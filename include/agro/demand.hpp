#pragma once
#include "agro/loop.hpp"
#include "agro/sha256.hpp"
#include <filesystem>
#include <functional>
#include <map>
#include <memory>
#include <set>
#include <tuple>

namespace agro::demand {
using namespace agro::loop;
inline std::vector<std::string> fields(const std::string &line) {
  std::vector<std::string> out;std::istringstream f(line);std::string x;
  while(std::getline(f,x,',')){if(!x.empty()&&x.back()=='\r')x.pop_back();out.push_back(x);}return out;
}
inline double number(const std::string &x) {
  size_t n=0;double v=std::stod(x,&n);require(n==x.size()&&std::isfinite(v),"invalid finite number: "+x);return v;
}
struct Settings {
  double horizon_s=3600,max_time_s=21600,capacity_kg=10,wait_s=60,balanced_tolerance_kg=2,deadline_reserve_s=15;
  double operator_period_s=600,operator_open_s=480,early_capacity_kg=20,buffer_units_per_station=10,buffer_unit_kg=1;
  double buffer_setup_s=8,buffer_per_unit_s=2,terminal_energy_tolerance_J=.1;
  static Settings load(const std::string &path) {
    Settings c;std::map<std::string,double*> keys;
#define K(k) keys[#k]=&c.k
    K(horizon_s);K(max_time_s);K(capacity_kg);K(wait_s);K(balanced_tolerance_kg);K(deadline_reserve_s);
    K(operator_period_s);K(operator_open_s);K(early_capacity_kg);K(buffer_units_per_station);K(buffer_unit_kg);
    K(buffer_setup_s);K(buffer_per_unit_s);K(terminal_energy_tolerance_J);
#undef K
    std::ifstream f(path);require(bool(f),"cannot open dispatch configuration");std::string key,value,line;
    while(std::getline(f,line)) {std::istringstream row(line);if(!(row>>key)||key[0]=='#')continue;
      require(bool(row>>value)&&keys.count(key),"unknown or malformed dispatch parameter: "+key);*keys.at(key)=number(value);}
    require(c.horizon_s>0&&c.max_time_s>c.horizon_s&&c.max_time_s<=21600,"dispatch horizon outside six-hour bound");
    require(c.capacity_kg>0&&c.capacity_kg<=10&&c.buffer_unit_kg==1&&c.buffer_units_per_station==10,"experimental capacity/buffer contract mismatch");
    require(c.operator_open_s>0&&c.operator_period_s>=c.operator_open_s&&c.wait_s>=0&&c.deadline_reserve_s>=0,"invalid dispatch times");
    require(c.early_capacity_kg>=0&&c.buffer_setup_s>=0&&c.buffer_per_unit_s>=0&&c.terminal_energy_tolerance_J>0,"invalid dispatch limits");return c;
  }
  double nextWindow(double now,double length) const {
    require(length>=0&&length<=operator_open_s,"operation cannot fit operator window");
    double begin=std::floor((now+1e-9)/operator_period_s)*operator_period_s;
    return now-begin+length<=operator_open_s+1e-8?now:begin+operator_period_s;
  }
};
struct Order {
  std::string id;double known=0,requested=0,deadline=0,mass=0,load=0,unload=0;
  int origin=0,state=0,carrier=-1;double loading_at=-1,loaded_at=-1,delivered_at=-1,fraction=0;
};
inline std::vector<Order> readOrders(const std::string &path,const Settings &c) {
  std::ifstream f(path);require(bool(f),"cannot open demand table");std::string line;std::getline(f,line);
  if(!line.empty()&&line.back()=='\r')line.pop_back();
  require(line=="id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s","unexpected demand columns");
  std::vector<Order> out;std::set<std::string> ids;
  while(std::getline(f,line)) {if(line.empty())continue;auto a=fields(line);require(a.size()==8,"demand row must have eight fields");Order o;o.id=a[0];
    require(!o.id.empty()&&o.id.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")==std::string::npos&&ids.insert(o.id).second,"invalid/duplicate order ID");
    o.known=number(a[1]);o.requested=number(a[2]);o.deadline=number(a[3]);double origin=number(a[4]);
    o.mass=number(a[5]);o.load=number(a[6]);o.unload=number(a[7]);
    require((origin==0||origin==1)&&o.known>=0&&o.known<=o.requested&&o.requested<c.horizon_s&&o.deadline>=o.requested,"invalid request chronology/origin");
    o.origin=int(origin);
    require(o.mass>0&&o.mass<=c.capacity_kg&&o.load>0&&o.unload>0&&o.load<=c.operator_open_s&&o.unload<=c.operator_open_s,"invalid load or handling duration");out.push_back(o);
  }return out;
}
// Sidecar is mandatory: old tables remain evidence and must be recalibrated.
inline std::string fileBytes(const std::string &path) {
  std::ifstream f(path,std::ios::binary);require(bool(f),"cannot open calibration input: "+path);
  return std::string(std::istreambuf_iterator<char>(f),{});
}
inline std::string predictorManifest(const std::string &path,const Config &c) {
#ifdef AGRO_CORE_ID
  return "agro-predictor-v1\ncore_sha256 " AGRO_CORE_ID "\nconfig_sha256 "+agro::sha256(c.canonical())+
    "\ntable_sha256 "+agro::sha256(fileBytes(path))+"\nmode central_only\nwind calm\ncells 363\n";
#else
  throw std::runtime_error("calibration requires a CMake build with core identity");
#endif
}
inline void writePredictorManifest(const std::string &path,const Config &c) {
  require(!std::filesystem::exists(path+".manifest"),"predictor manifest already exists");
  std::ofstream f(path+".manifest",std::ios::binary);f<<predictorManifest(path,c);f.close();
  require(bool(f),"cannot write predictor manifest");
}
struct Estimate {double positive=0,absorbed=0,duration=0;};
class Predictor {
  std::map<std::tuple<std::string,int,int>,Estimate> table;
 public:
  void load(const std::string &path,const Config &c) {
    require(fileBytes(path+".manifest")==predictorManifest(path,c),"predictor calibration mismatch; recalibrate for this configuration/core/table");
    table.clear();
    std::ifstream f(path);require(bool(f),"cannot open calibrated predictor");std::string line;std::getline(f,line);
    if(!line.empty()&&line.back()=='\r')line.pop_back();
    require(line=="leg_kind,up_kg,down_kg,positive_J,absorbed_J,duration_s","unexpected predictor columns");
    while(std::getline(f,line)){if(line.empty())continue;auto a=fields(line);require(a.size()==6,"invalid predictor row");double u=number(a[1]),d=number(a[2]);
      require((a[0]=="first"||a[0]=="upper0"||a[0]=="lower0")&&u>=0&&u<=10&&d>=0&&d<=10&&u==std::floor(u)&&d==std::floor(d),"invalid predictor coordinate");
      Estimate e{number(a[3]),number(a[4]),number(a[5])};require(e.positive>=0&&e.absorbed>=0&&e.duration>0,"invalid predictor estimate");
      require(table.emplace(std::make_tuple(a[0],int(u),int(d)),e).second,"duplicate predictor coordinate");}
    require(table.size()==363,"predictor must contain all 363 calibrated cells");
  }
  Estimate at(const std::string &kind,double up,double down) const {
    require(up>=-1e-9&&up<=10+1e-9&&down>=-1e-9&&down<=10+1e-9,"predictor outside calibration range");
    up=std::clamp(up,0.,10.);down=std::clamp(down,0.,10.);int u0=int(std::floor(up)),d0=int(std::floor(down)),u1=std::min(10,u0+1),d1=std::min(10,d0+1);
    double fu=up-u0,fd=down-d0;Estimate e;
    for(auto u:{std::pair<int,double>{u0,1-fu},{u1,fu}})for(auto d:{std::pair<int,double>{d0,1-fd},{d1,fd}}){const auto &a=table.at({kind,u.first,d.first});double w=u.second*d.second;e.positive+=w*a.positive;e.absorbed+=w*a.absorbed;e.duration+=w*a.duration;}
    return e;
  }
};
struct Module {int id=0,home=0,station=0,carrier=-1;double fraction=0;bool reserved=false;};
struct Action {bool load=false,aux=false;int order=-1;std::vector<int> modules;double mass=0,length=0,start=-1,before=0;};
struct Candidate {std::array<std::vector<int>,2> jobs,aux;std::array<double,2> useful{0,0};double cost=0,handling=0,total_mass=0,lateness=0;int late_count=0;};
class Engine:public Program {
  Simulation &s;Settings cfg;Predictor predictor;std::vector<Order> orders;std::vector<Module> modules;
  int policy=0;bool compact=false,finished=false,successful=false,comparable=false,restoring=false,homing=false,settling=false;
  std::array<int,2> stations{0,1};std::array<std::vector<Action>,2> actions;std::array<size_t,2> action_index{0,0};
  std::array<std::vector<int>,2> manifest_orders,manifest_aux;
  std::unique_ptr<Leg> leg;double leg_start=0,leg_origin=0,hold_q=0,leg_predicted=0,leg_positive=0,leg_absorbed=0;
  double wait_start=-1,settle_start=-1,restoration_start=-1,restoration_work=0,deliberate_wait=0,mandatory_wait=0,buffer_moves=0,predictor_error=0,last_status=-1,next_dispatch=-1;
  double terminal_delta=0,peak_energy_residual=0;int trip_count=0;std::string current_kind,status_value="interrupted";
  double handling_time=0;std::array<double,2> operator_busy{0,0};bool any_action_active=false;
  std::filesystem::path folder;std::ofstream orderlog,triplog,oplog,invlog,statuslog;
  double next_decision=0;
  bool buffering() const {return policy>=2;}
  bool waiting() const {return policy==1||policy==3;}
  int carrierAt(int station) const {return stations[0]==station?0:1;}
  double mass(const std::vector<int>& ids) const {double v=0;for(int i:ids)v+=orders[i].mass;return v;}
  bool allDelivered() const {for(const auto &o:orders)if(o.state!=4)return false;return true;}
  bool stocksRestored() const {for(const auto &m:modules)if(m.station!=m.home||m.carrier!=-1||m.reserved)return false;return true;}
  std::vector<int> available(int station,bool early,double time) const {
    std::vector<int> result,candidates;double stock=0;
    if(early){for(size_t i=0;i<orders.size();++i){const auto&o=orders[i];if(o.origin==station&&o.state==0&&o.known<=time+1e-9&&o.requested>time+1e-9)candidates.push_back(int(i));}
      std::sort(candidates.begin(),candidates.end(),[&](int a,int b){return std::tie(orders[a].known,orders[a].id)<std::tie(orders[b].known,orders[b].id);});
      for(int i:candidates)if(stock+orders[i].mass<=cfg.early_capacity_kg+1e-9){stock+=orders[i].mass;result.push_back(i);}
    }else for(size_t i=0;i<orders.size();++i){const auto&o=orders[i];if(o.origin==station&&o.state==0&&o.known<=time+1e-9&&o.requested<=time+1e-9)result.push_back(int(i));}
    std::sort(result.begin(),result.end(),[&](int a,int b){return std::tie(orders[a].deadline,orders[a].requested,orders[a].id)<std::tie(orders[b].deadline,orders[b].requested,orders[b].id);});return result;
  }
  std::vector<int> availableModules(int station) const {
    std::vector<int> ids;for(const auto &m:modules)if(m.station==station&&m.carrier<0&&!m.reserved)ids.push_back(m.id);
    std::sort(ids.begin(),ids.end(),[&](int a,int b){return std::make_pair(modules[a].home==station,a)<std::make_pair(modules[b].home==station,b);});return ids;
  }
  std::string legKind() const {return trip_count==0&&hold_q<1e-8?"first":stations[0]==1?"upper0":"lower0";}
  double legDistance() const {return trip_count==0&&hold_q<1e-8?s.route.lane_length:s.route.total/2;}
  bool stopped() const {
    if(std::abs(s.q-hold_q)>=s.c.station_tolerance||std::abs(s.v)>=s.c.stop_speed)return false;
    for(const auto &a:s.carts)if(std::abs(a.offset_speed)>=s.c.stop_speed||std::abs(s.q-hold_q+a.offset)>=s.c.station_tolerance)return false;
    return true;
  }
  double handlingFinish(double time,const std::vector<int>&jobs,int aux,bool load) const {
    for(int i:jobs){double dt=load?orders[i].load:orders[i].unload;time=cfg.nextWindow(time,dt)+dt;}
    if(aux){double dt=cfg.buffer_setup_s+cfg.buffer_per_unit_s*aux;time=cfg.nextWindow(time,dt)+dt;}return time;
  }
  Candidate baseCandidate(double time) const {
    Candidate c;for(int station=0;station<2;++station)for(int i:available(station,false,time))if(c.useful[station]+orders[i].mass<=cfg.capacity_kg+1e-9){c.jobs[station].push_back(i);c.useful[station]+=orders[i].mass;}return c;
  }
  double earlyStock(int station,double time) const {return mass(available(station,true,time));}
  // Feasible fallback schedule for ALL already announced work. This deliberately
  // adds neither future announcements nor further optional waits/auxiliary loads.
  // The energy objective still has its declared two-leg horizon; deadline
  // protection must not silently discard known work beyond that horizon.
  std::map<int,double> knownCompletions(Candidate batch,double time,double knowledge_time) const {
    std::set<int> remaining;
    for(size_t i=0;i<orders.size();++i)
      if(orders[i].state==0&&orders[i].known<=knowledge_time+1e-9)remaining.insert(int(i));
    std::map<int,double> completion;
    std::string kind=legKind();
    while(!remaining.empty()) {
      if(batch.jobs[0].empty()&&batch.jobs[1].empty()) {
        double release=std::numeric_limits<double>::infinity();
        for(int id:remaining)release=std::min(release,orders[id].requested);
        time=std::max(time,release);
        for(int st=0;st<2;++st) {
          std::vector<int> ready;
          for(int id:remaining)if(orders[id].origin==st&&orders[id].requested<=time+1e-9)ready.push_back(id);
          std::sort(ready.begin(),ready.end(),[&](int a,int b){return std::tie(orders[a].deadline,orders[a].requested,orders[a].id)<std::tie(orders[b].deadline,orders[b].requested,orders[b].id);});
          for(int id:ready)if(batch.useful[st]+orders[id].mass<=cfg.capacity_kg+1e-9){batch.jobs[st].push_back(id);batch.useful[st]+=orders[id].mass;}
        }
        require(!batch.jobs[0].empty()||!batch.jobs[1].empty(),"known-order deadline forecast stalled");
      }
      double depart=std::max(handlingFinish(time,batch.jobs[0],int(batch.aux[0].size()),true),handlingFinish(time,batch.jobs[1],int(batch.aux[1].size()),true));
      double arrival=depart+predictor.at(kind,batch.useful[0]+batch.aux[0].size(),batch.useful[1]+batch.aux[1].size()).duration;
      double next=arrival;
      for(int st=0;st<2;++st) {
        double done=arrival;
        for(int id:batch.jobs[st]) {
          require(remaining.erase(id)==1,"deadline forecast contains unknown or repeated work");
          done=cfg.nextWindow(done,orders[id].unload)+orders[id].unload;
          completion[id]=done;
        }
        if(!batch.aux[st].empty()){double length=cfg.buffer_setup_s+cfg.buffer_per_unit_s*batch.aux[st].size();done=cfg.nextWindow(done,length)+length;}
        next=std::max(next,done);
      }
      time=next;kind=kind=="upper0"?"lower0":"upper0";batch=Candidate{};
    }
    return completion;
  }
  Candidate choose(double time) const {
    Candidate base=baseCandidate(time);if(!buffering()||(base.jobs[0].empty()&&base.jobs[1].empty()))return base;
    // Evaluate identical mandatory work across candidates, using only announcements
    // already visible at time. Optional early loads may not sacrifice feasible work.
    auto evaluate=[&](Candidate &c){std::map<int,double> completion;
      double up=c.useful[0]+c.aux[0].size(),down=c.useful[1]+c.aux[1].size();
      auto first=predictor.at(legKind(),up,down);
      double depart=std::max(handlingFinish(time,c.jobs[0],int(c.aux[0].size()),true),handlingFinish(time,c.jobs[1],int(c.aux[1].size()),true));
      double arrival=depart+first.duration,next_ready=arrival;
      for(int st=0;st<2;++st){double t=arrival;for(int id:c.jobs[st]){t=cfg.nextWindow(t,orders[id].unload)+orders[id].unload;completion[id]=t;}
        if(!c.aux[st].empty()){double dt=cfg.buffer_setup_s+cfg.buffer_per_unit_s*c.aux[st].size();t=cfg.nextWindow(t,dt)+dt;}next_ready=std::max(next_ready,t);}
      std::set<int> selected(c.jobs[0].begin(),c.jobs[0].end());selected.insert(c.jobs[1].begin(),c.jobs[1].end());
      std::array<std::vector<int>,2> next_jobs;std::array<double,2> next_mass{0,0};
      for(int st=0;st<2;++st){std::vector<int> known;for(size_t i=0;i<orders.size();++i)if(orders[i].state==0&&orders[i].origin==st&&orders[i].known<=time+1e-9&&orders[i].requested<=next_ready+1e-9&&!selected.count(int(i)))known.push_back(int(i));
        std::sort(known.begin(),known.end(),[&](int x,int y){return std::tie(orders[x].deadline,orders[x].requested,orders[x].id)<std::tie(orders[y].deadline,orders[y].requested,orders[y].id);});
        for(int i:known)if(next_mass[st]+orders[i].mass<=cfg.capacity_kg+1e-9){next_jobs[st].push_back(i);next_mass[st]+=orders[i].mass;}}
      int return_up=std::min<int>(c.aux[1].size(),int(cfg.capacity_kg-next_mass[0])),return_down=std::min<int>(c.aux[0].size(),int(cfg.capacity_kg-next_mass[1]));
      std::string following=stations[0]==0?"upper0":"lower0";
      auto second=predictor.at(following,next_mass[0]+return_up,next_mass[1]+return_down);
      double next_depart=std::max(handlingFinish(next_ready,next_jobs[0],return_up,true),handlingFinish(next_ready,next_jobs[1],return_down,true));
      double next_arrival=next_depart+second.duration;
      for(int st=0;st<2;++st){double t=next_arrival;for(int id:next_jobs[st]){t=cfg.nextWindow(t,orders[id].unload)+orders[id].unload;completion[id]=t;}}
      int remaining_up=int(c.aux[1].size())-return_up,remaining_down=int(c.aux[0].size())-return_down;
      double restoration=0;
      if(remaining_up||remaining_down){std::string third=stations[0]==0?"lower0":"upper0";
        // An additional empty positioning leg and the residual restoration leg
        // are paid explicitly; auxiliary return never borrows a free useful trip.
        restoration=predictor.at(third,0,0).positive+predictor.at(following,remaining_up,remaining_down).positive;}
      c.cost=first.positive+second.positive+restoration;c.handling=(depart-time)+(next_ready-arrival)+(next_depart-next_ready);
      c.total_mass=up+down;return completion;};
    evaluate(base);
    auto mandatory=knownCompletions(base,time,time);
    std::array<std::vector<std::vector<int>>,2> choices;
    for(int st=0;st<2;++st){choices[st].push_back(base.jobs[st]);auto ids=base.jobs[st];double weight=base.useful[st];
      for(int i:available(st,true,time))if(weight+orders[i].mass<=cfg.capacity_kg+1e-9){ids.push_back(i);weight+=orders[i].mass;choices[st].push_back(ids);}}
    Candidate best=base;best.late_count=0;best.lateness=0;
    for(const auto &entry:mandatory){double late=std::max(0.,entry.second-orders[entry.first].deadline);best.late_count+=late>1e-9;best.lateness+=late;}
    auto pool0=availableModules(0),pool1=availableModules(1);
    for(const auto &j0:choices[0])for(const auto &j1:choices[1]){
      std::array<double,2>w{mass(j0),mass(j1)};
      for(int a=0;a<=std::min<int>(pool0.size(),int(std::floor(cfg.capacity_kg-w[0]+1e-9)));++a)
      for(int b=0;b<=std::min<int>(pool1.size(),int(std::floor(cfg.capacity_kg-w[1]+1e-9)));++b){
        Candidate c;c.jobs={j0,j1};c.useful=w;c.aux[0].assign(pool0.begin(),pool0.begin()+a);c.aux[1].assign(pool1.begin(),pool1.begin()+b);
        evaluate(c);auto completion=knownCompletions(c,time,time);bool sacrifices_feasible=false;
        for(const auto &entry:mandatory){auto it=completion.find(entry.first);double done=it==completion.end()?cfg.max_time_s:it->second;
          double late=std::max(0.,done-orders[entry.first].deadline);c.late_count+=late>1e-9;c.lateness+=late;
          if(entry.second<=orders[entry.first].deadline+1e-9&&done>orders[entry.first].deadline+1e-9)sacrifices_feasible=true;}
        if(!sacrifices_feasible&&std::tie(c.late_count,c.lateness,c.cost,c.handling,c.total_mass)<std::tie(best.late_count,best.lateness,best.cost,best.handling,best.total_mass))best=std::move(c);
      }}return best;
  }
  bool dispatchNow(const Candidate &c,double time) {
    if(c.jobs[0].empty()&&c.jobs[1].empty())return false;
    if(!waiting())return true;
    if(wait_start<0)wait_start=time;
    if(c.useful[0]>0&&c.useful[1]>0&&std::abs(c.useful[0]-c.useful[1])<=cfg.balanced_tolerance_kg)return true;
    if(time-wait_start>=cfg.wait_s-1e-9)return true;
    // Look one decision tick ahead, including integration quantization. This
    // catches an operator-window discontinuity before the last fitting start.
    double next_check=time+std::min(1+s.c.dt,std::max(0.,wait_start+cfg.wait_s-time));
    auto completion=knownCompletions(c,next_check,time);
    for(const auto &entry:completion)
      if(entry.second+cfg.deadline_reserve_s>=orders[entry.first].deadline)return true;
    next_dispatch=wait_start+cfg.wait_s;return false;
  }
  void inventory(double now) {for(const auto&m:modules)invlog<<now<<','<<m.id<<','<<m.home<<','<<m.station<<','<<m.carrier<<','<<m.fraction<<','<<m.reserved<<'\n';}
  void planLoad(const Candidate &c) {
    for(int st=0;st<2;++st){int car=carrierAt(st);actions[car].clear();action_index[car]=0;manifest_orders[car]=c.jobs[st];manifest_aux[car]=c.aux[st];
      for(int i:c.jobs[st]){orders[i].state=1;orders[i].carrier=car;actions[car].push_back({true,false,i,{},orders[i].mass,orders[i].load});}
      if(!c.aux[st].empty()){for(int id:c.aux[st])modules[id].reserved=true;actions[car].push_back({true,true,-1,c.aux[st],double(c.aux[st].size()),cfg.buffer_setup_s+cfg.buffer_per_unit_s*c.aux[st].size()});}}
    wait_start=-1;next_dispatch=-1;s.stage=2;
  }
  void planUnload() {
    for(int car=0;car<2;++car){actions[car].clear();action_index[car]=0;
      for(int i:manifest_orders[car]){orders[i].state=3;actions[car].push_back({false,false,i,{},orders[i].mass,orders[i].unload});}
      if(!manifest_aux[car].empty())actions[car].push_back({false,true,-1,manifest_aux[car],double(manifest_aux[car].size()),cfg.buffer_setup_s+cfg.buffer_per_unit_s*manifest_aux[car].size()});}
    s.stage=4;
  }
  bool operate(double h) {
    any_action_active=false;
    bool all=true;for(int car=0;car<2;++car){if(action_index[car]>=actions[car].size())continue;all=false;auto &a=actions[car][action_index[car]];
      if(a.start<0){double start=cfg.nextWindow(s.t,a.length);if(start>s.t+1e-9)continue;require(stopped(),"demand operation requires stopped carriers");a.start=s.t;a.before=s.carts[car].payload;
        if(a.order>=0&&a.load)orders[a.order].loading_at=s.t;
        oplog<<s.t<<",begin,"<<car<<','<<stations[car]<<','<<(a.load?"load":"unload")<<','<<(a.aux?"aux":orders[a.order].id)<<','<<a.mass<<','<<a.length<<'\n';}
      require(stopped(),"demand carrier moved during handling");double u=smooth((s.t+h-a.start)/s.c.payload_ramp),before=s.carts[car].payload;
      double active=std::max(0.,std::min(h,a.start+a.length-s.t));
      operator_busy[stations[car]]+=active;any_action_active=any_action_active||active>0;
      s.carts[car].payload=a.before+(a.load?1:-1)*a.mass*u;
      if(std::abs(s.carts[car].payload)<1e-12)s.carts[car].payload=0;
      s.load_energy+=(s.carts[car].payload-before)*s.payloadSpecificEnergy(car);
      if(a.order>=0)orders[a.order].fraction=a.load?u:1-u;
      for(int id:a.modules)modules[id].fraction=a.load?u:1-u;
      if(s.t+h-a.start>=a.length-1e-9){double end=s.t+h;
        if(a.order>=0){auto &o=orders[a.order];if(a.load){o.state=2;o.loaded_at=end;}else{o.state=4;o.delivered_at=end;o.carrier=-1;}}
        for(int id:a.modules){auto&m=modules[id];m.carrier=a.load?car:-1;m.station=a.load?-1:stations[car];m.reserved=false;if(a.load)buffer_moves+=1;}
        oplog<<end<<",end,"<<car<<','<<stations[car]<<','<<(a.load?"load":"unload")<<','<<(a.aux?"aux":orders[a.order].id)<<','<<a.mass<<','<<a.length<<'\n';
        ++action_index[car];inventory(end);
      }}return all;
  }
  void depart(bool home=false) {
    double distance=home?std::ceil((hold_q-1e-8)/s.route.total)*s.route.total-hold_q:legDistance();
    if(home&&distance<1e-8){settling=true;settle_start=s.t;return;}
    leg=std::make_unique<Leg>(distance,s.c);leg_origin=hold_q;leg_start=s.t;homing=home;current_kind=home?"home":legKind();
    double up=s.carts[carrierAt(0)].payload,down=s.carts[carrierAt(1)].payload;
    leg_predicted=home?0:predictor.at(current_kind,up,down).positive;leg_positive=s.drive_positive;leg_absorbed=s.drive_absorbed;
    triplog<<trip_count<<",begin,"<<s.t<<','<<current_kind<<','<<hold_q<<','<<distance<<','<<up<<','<<down<<','<<leg_predicted<<",0,0,"<<restoring<<'\n';
    ++trip_count;s.stage=3;
  }
  void beginRestoration() {if(!restoring){restoring=true;restoration_start=s.t;restoration_work=s.drive_positive;wait_start=-1;}}
  void restorationDecision() {
    if(stocksRestored()){depart(true);return;}
    Candidate c;for(int st=0;st<2;++st)for(int id:availableModules(st))if(modules[id].home!=st&&c.aux[st].size()<size_t(cfg.capacity_kg))c.aux[st].push_back(id);
    require(!c.aux[0].empty()||!c.aux[1].empty(),"buffer restoration stalled");planLoad(c);
  }
 public:
  Engine(Simulation &simulation,const std::string &demand,const std::string &settings,const std::string &policy_name,const std::string &prediction,const std::string &output,bool sparse=false):s(simulation),cfg(Settings::load(settings)),compact(sparse),folder(output) {
    require(s.c.single_span&&s.carts.size()==2&&!s.hybrid&&!s.gust,"demand pilot requires two-carrier central_only calm model");
    require(policy_name.size()==1&&policy_name[0]>='A'&&policy_name[0]<='D',"policy must be A/B/C/D");policy=policy_name[0]-'A';orders=readOrders(demand,cfg);predictor.load(prediction,s.c);
    for(const auto &o:orders)require(o.load>=s.c.payload_ramp&&o.unload>=s.c.payload_ramp,"handling shorter than payload_ramp");
    require(cfg.buffer_setup_s+cfg.buffer_per_unit_s>=s.c.payload_ramp,"auxiliary handling shorter than payload_ramp");
    for(int i=0;i<20;++i)modules.push_back({i,i<10?0:1,i<10?0:1,-1,0,false});
    std::filesystem::create_directories(folder);
    for(auto name:{"orders.csv","trips.csv","operations.csv","inventory.csv","demand_status.csv","demand_summary.json"})require(!std::filesystem::exists(folder/name),"demand output already exists");
    orderlog.open(folder/"orders.csv");triplog.open(folder/"trips.csv");oplog.open(folder/"operations.csv");invlog.open(folder/"inventory.csv");statuslog.open(folder/"demand_status.csv");
    require(bool(orderlog)&&bool(triplog)&&bool(oplog)&&bool(invlog)&&bool(statuslog),"cannot create demand logs");
    orderlog<<"id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s,load_start_s,loaded_s,delivered_s,lateness_s,state\n";
    triplog<<"trip,event,time_s,leg_kind,q_start_m,distance_m,up_kg,down_kg,predicted_positive_J,actual_positive_J,actual_absorbed_J,restoration\n";
    oplog<<"time_s,event,carrier,station,operation,order_or_aux,mass_kg,duration_s\n";
    invlog<<"time_s,module_id,home,station,carrier,aboard_fraction,reserved\n";
    statuslog<<"time_s,policy,phase,queue_up,queue_down,slack_up_s,slack_down_s,next_dispatch_s,operator_lower,operator_upper,useful_0_kg,useful_1_kg,aux_0_kg,aux_1_kg,inventory_lower_kg,inventory_upper_kg,early_lower_kg,early_upper_kg,delivered_orders,late_orders\n";
    for(auto*f:{&orderlog,&triplog,&oplog,&invlog,&statuslog})*f<<std::setprecision(12);
    s.program=this;s.stage=0;inventory(0);record(true);
  }
  ~Engine() override {s.program=nullptr;}
  Motion reference(double time) const override {if(!leg)return {hold_q,0,0};auto m=leg->at(time-leg_start);m.s+=leg_origin;return m;}
  double duration() const override {return cfg.max_time_s;}
  void beforeStep(Simulation &,double h) override {
    if(leg){if(s.t<leg_start+leg->duration-1e-9)return;hold_q=leg_origin+leg->distance;if(!stopped()){mandatory_wait+=h;return;}
      double actual=s.drive_positive-leg_positive;if(!homing)predictor_error+=std::abs(actual-leg_predicted);
      triplog<<trip_count-1<<",end,"<<s.t<<','<<current_kind<<','<<leg_origin<<','<<leg->distance<<','<<s.carts[carrierAt(0)].payload<<','<<s.carts[carrierAt(1)].payload<<','<<leg_predicted<<','<<actual<<','<<s.drive_absorbed-leg_absorbed<<','<<restoring<<'\n';
      leg.reset();if(homing){settling=true;settle_start=s.t;return;}stations[0]=1-stations[0];stations[1]=1-stations[1];planUnload();return;}
    if(settling){s.stage=5;mandatory_wait+=h;return;}
    if(s.stage==2||s.stage==4){bool loading=s.stage==2;bool done=operate(h);if(!done){if(any_action_active)handling_time+=h;else mandatory_wait+=h;return;}
      if(loading){depart();return;}for(int car=0;car<2;++car){manifest_orders[car].clear();manifest_aux[car].clear();}s.stage=0;return;}
    if(!stopped()){mandatory_wait+=h;return;}
    if(s.t+1e-9<next_decision){if(s.stage==1)deliberate_wait+=h;return;}
    next_decision=s.t+1;
    // Wake exactly for announced/released orders and the waiting deadline.
    for(const auto&o:orders)if(o.state==0){if(o.known>s.t+1e-9)next_decision=std::min(next_decision,o.known);if(o.known<=s.t+1e-9&&o.requested>s.t+1e-9)next_decision=std::min(next_decision,o.requested);}
    if(wait_start>=0&&wait_start+cfg.wait_s>s.t+1e-9)next_decision=std::min(next_decision,wait_start+cfg.wait_s);
    if(cfg.horizon_s>s.t+1e-9)next_decision=std::min(next_decision,cfg.horizon_s);
    if(s.t>=cfg.horizon_s&&allDelivered()){beginRestoration();restorationDecision();return;}
    Candidate c=choose(s.t);
    if(c.jobs[0].empty()&&c.jobs[1].empty()){s.stage=0;wait_start=-1;next_dispatch=-1;return;}
    if(dispatchNow(c,s.t)){planLoad(c);return;}s.stage=1;deliberate_wait+=h;
  }
  // Numerical terminal ledger budget for the calm central-only demand pilot.
  // Transient residual is reported separately: omitted shape-rate terms remain.
  double energyBudget() const {return .5+.01*(s.drive_positive+s.drive_absorbed+s.loss_work);}
  bool energyAccepted() const {
    return std::isfinite(s.residual())&&std::isfinite(energyBudget())&&
      std::abs(s.residual())<=energyBudget()&&std::abs(s.energy()-s.energy0)<=std::min(.1,cfg.terminal_energy_tolerance_J);
  }
  void afterStep(Simulation &) override {
    peak_energy_residual=std::max(peak_energy_residual,std::abs(s.residual()));
    if(settling){terminal_delta=s.energy()-s.energy0;bool at_rest=stopped()&&std::abs(s.v)<1e-4;
      for(const auto &a:s.carts)at_rest=at_rest&&std::abs(a.offset_speed)<1e-4&&std::abs(a.wx)<1e-3&&std::abs(a.wy)<1e-3;
      if(std::abs(terminal_delta)<=cfg.terminal_energy_tolerance_J&&s.t-settle_start>=2&&at_rest){double stops=0;for(const auto&a:s.carts)stops+=a.stops;
        successful=true;comparable=stops==0&&energyAccepted();finished=true;status_value=comparable?"completed":"completed_noncomparable";s.complete=true;s.stage=6;}
      else if(s.t-settle_start>=120){successful=true;comparable=false;finished=true;status_value="completed_noncomparable";s.complete=true;s.stage=6;}}
    if(s.t>=cfg.max_time_s-1e-8&&!finished){terminal_delta=s.energy()-s.energy0;finished=true;successful=allDelivered()&&stocksRestored()&&settling;comparable=false;status_value=successful?"completed_noncomparable":"failed";s.complete=true;s.stage=6;}
    validateConservation();record(s.complete);
  }
  void validateConservation() const {
    std::array<double,2> aboard{0,0};for(const auto&o:orders)if(o.carrier>=0)aboard[o.carrier]+=o.mass*o.fraction;
    std::set<int> ids;for(const auto&m:modules){require(ids.insert(m.id).second&&m.fraction>=-1e-8&&m.fraction<=1+1e-8,"module conservation/identity failed");
      int car=m.carrier;if(car<0&&m.reserved){for(int i=0;i<2;++i)if(std::find(manifest_aux[i].begin(),manifest_aux[i].end(),m.id)!=manifest_aux[i].end())car=i;}
      if(car>=0)aboard[car]+=m.fraction;}
    for(int car=0;car<2;++car)require(std::abs(aboard[car]-s.carts[car].payload)<1e-8&&aboard[car]<=cfg.capacity_kg+1e-8&&aboard[car]>=-1e-8,"physical payload/manifest mass mismatch");
  }
  void record(bool force=false) {
    if(!force&&s.t-last_status<(compact?5:s.c.log_period)-1e-8)return;
    last_status=s.t;
    std::array<int,2> queue{0,0};std::array<double,2>slack{-1,-1},useful{0,0},aux{0,0},inventory_kg{0,0};int done=0,late=0;
    for(const auto&o:orders){if(o.state==0&&o.requested<=s.t+1e-9&&o.known<=s.t+1e-9){++queue[o.origin];double z=o.deadline-s.t;if(slack[o.origin]==-1||z<slack[o.origin])slack[o.origin]=z;}
      if(o.carrier>=0)useful[o.carrier]+=o.mass*o.fraction;
      if(o.state==4){++done;late+=o.delivered_at>o.deadline+1e-8;}}
    for(const auto&m:modules){if(m.station>=0)inventory_kg[m.station]+=1-m.fraction;else if(m.carrier>=0)inventory_kg[stations[m.carrier]]+=1-m.fraction;int car=m.carrier;
      if(car<0&&m.reserved)for(int i=0;i<2;++i)if(std::find(manifest_aux[i].begin(),manifest_aux[i].end(),m.id)!=manifest_aux[i].end())car=i;
      if(car>=0)aux[car]+=m.fraction;}
    int phase=finished?6:restoring?5:s.stage;bool op=std::fmod(s.t,cfg.operator_period_s)<cfg.operator_open_s;
    statuslog<<s.t<<','<<policy<<','<<phase<<','<<queue[0]<<','<<queue[1]<<','<<slack[0]<<','<<slack[1]<<','<<next_dispatch<<','<<op<<','<<op<<','<<useful[0]<<','<<useful[1]<<','<<aux[0]<<','<<aux[1]<<','<<inventory_kg[0]<<','<<inventory_kg[1]<<','<<earlyStock(0,s.t)<<','<<earlyStock(1,s.t)<<','<<done<<','<<late<<'\n';
  }
  bool completed() const {return successful;}
  double loadedMass() const override {double total=0;for(const auto&o:orders)if(o.loaded_at>=0)total+=o.mass;return total;}
  double unloadedMass() const override {double total=0;for(const auto&o:orders)if(o.delivered_at>=0)total+=o.mass;return total;}
  bool isComparable() const {return comparable;}
  std::string status() const {return status_value;}
  void finish(const std::string &fallback="interrupted") {
    if(!finished)status_value=fallback;
    record(true);std::vector<double>lateness;int done=0,ontime=0;double total=0,delivered=0,ontime_mass=0,maximum=0;
    for(const auto&o:orders){double late=o.state==4?std::max(0.,o.delivered_at-o.deadline):-1;total+=o.mass;
      if(o.state==4){++done;delivered+=o.mass;lateness.push_back(late);maximum=std::max(maximum,late);if(late<=1e-8){++ontime;ontime_mass+=o.mass;}}
      orderlog<<o.id<<','<<o.known<<','<<o.requested<<','<<o.deadline<<','<<o.origin<<','<<o.mass<<','<<o.load<<','<<o.unload<<','<<o.loading_at<<','<<o.loaded_at<<','<<o.delivered_at<<','<<late<<','<<o.state<<'\n';}
    std::sort(lateness.begin(),lateness.end());double p95=lateness.empty()?0:lateness[size_t(std::ceil(.95*lateness.size()))-1];double stops=0;for(const auto&a:s.carts)stops+=a.stops;
    std::ofstream f(folder/"demand_summary.json");f<<std::setprecision(12)<<"{\n\"schema\":\"agro-demand-v1\",\n\"policy\":\""<<char('A'+policy)<<"\",\n\"status\":\""<<status_value<<"\",\n\"comparable\":"<<(comparable?"true":"false")<<",\n\"completed\":"<<(successful?"true":"false")<<",\n";
#define J(k,v) f<<"\""<<k<<"\":"<<(v)<<",\n"
    J("orders_total",orders.size());J("orders_delivered",done);J("on_time_orders",ontime);J("on_time_mass_kg",ontime_mass);J("total_useful_kg",total);J("delivered_useful_kg",delivered);
    J("lateness_p95_s",p95);J("max_lateness_s",maximum);J("deliberate_wait_s",deliberate_wait);J("mandatory_wait_s",mandatory_wait);J("trips",trip_count);J("buffer_moves_kg",buffer_moves);
    J("handling_s",handling_time);J("operator_busy_lower_s",operator_busy[0]);J("operator_busy_upper_s",operator_busy[1]);
    J("restoration_positive_J",restoring?s.drive_positive-restoration_work:0);J("restoration_time_s",restoring?s.t-restoration_start:0);J("energy_delta_J",s.energy()-s.energy0);J("simulation_s",s.t);
    f<<"\"energy_acceptance_schema\":\"agro-demand-energy-v1\",\n";
    f<<"\"energy_accepted\":"<<((successful&&comparable&&energyAccepted())?"true":"false")<<",\n";
    J("energy_residual_budget_J",energyBudget());J("peak_abs_energy_residual_J",peak_energy_residual);
    J("drive_positive_J",s.drive_positive);J("drive_absorbed_J",s.drive_absorbed);J("loss_work_J",s.loss_work);J("load_energy_J",s.load_energy);J("residual_J",s.residual());J("predictor_absolute_error_J",predictor_error);
#undef J
    f<<"\"governor_or_stop_count\":"<<stops<<"\n}\n";for(auto*p:{&orderlog,&triplog,&oplog,&invlog,&statuslog})p->flush();
  }
};

class CalibrationProgram:public Program {
  double origin,start=0;Leg leg;double end;
 public:
  CalibrationProgram(double q,double distance,const Config &c):origin(q),leg(distance,c),end(leg.duration+2){}
  Motion reference(double t) const override {auto m=leg.at(t-start);m.s+=origin;return m;}
  double duration()const override{return end;}
  void beforeStep(Simulation&s,double)override{s.stage=3;}
  void afterStep(Simulation&s)override{if(s.t>=end-1e-8)s.complete=true;}
  double travelTime()const{return leg.duration;}
};
inline void buildPredictor(Config c,const std::string &output) {
  require(c.single_span&&c.carriers_per_lane==1,"predictor needs two-carrier topology");
  std::filesystem::create_directories(output);auto path=std::filesystem::path(output)/"predictor.csv";require(!std::filesystem::exists(path)&&!std::filesystem::exists(path.string()+".manifest"),"predictor output already exists");
  std::ofstream f(path);f<<"leg_kind,up_kg,down_kg,positive_J,absorbed_J,duration_s\n"<<std::setprecision(12);
  for(std::string kind:{"first","upper0","lower0"})for(int up=0;up<=10;++up)for(int down=0;down<=10;++down){Simulation sim(c,false,false);
    sim.q=kind=="first"?0:kind=="upper0"?sim.route.lane_length:2*sim.route.lane_length+pi*c.lane_half_width;
    sim.carts[0].payload=kind=="upper0"?down:up;sim.carts[1].payload=kind=="upper0"?up:down;
    for(int i=0;i<24;++i){sim.updateShape();for(size_t j=0;j<sim.carts.size();++j)sim.carts[j].offset=.5*sim.carts[j].offset-.5*(c.tare()+sim.carts[j].payload)*g*sim.path_d[j].z/c.coupling_k;}
    sim.updateShape();sim.refreshPositions();sim.energy0=sim.energy();CalibrationProgram program(sim.q,kind=="first"?sim.route.lane_length:sim.route.total/2,c);sim.program=&program;
    while(!sim.complete)sim.step(c.dt);
    double stops=0;for(const auto &cart:sim.carts)stops+=cart.stops;require(stops==0,"predictor calibration activated ideal stops/governor");
    f<<kind<<','<<up<<','<<down<<','<<sim.drive_positive<<','<<sim.drive_absorbed<<','<<program.travelTime()<<'\n';sim.program=nullptr;
  }
  f.close();require(bool(f),"cannot write predictor table");writePredictorManifest(path.string(),c);
}
}
