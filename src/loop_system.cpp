#include "agro/loop_log.hpp"
#include <gz/sim/System.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/EventManager.hh>
#include <gz/sim/Events.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/Model.hh>
#include <gz/plugin/Register.hh>
#include <gz/transport/Node.hh>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/common/Console.hh>
#include <map>
#include <memory>

namespace agro {
// Live integration of the SAME reduced model tested by loop_cli. Gazebo only
// renders states; native gravity/contact is not applied a second time.
class LoopSystem: public gz::sim::System,public gz::sim::ISystemConfigure,
                  public gz::sim::ISystemPreUpdate,public gz::sim::ISystemReset {
  std::unique_ptr<loop::Simulation> sim;
  std::unique_ptr<loop::Log> log;
  gz::sim::EventManager *events=nullptr;
  gz::transport::Node node;
  gz::transport::Node::Publisher status;
  std::map<std::string,gz::sim::Entity> entities;
  std::string params,output,mode;
  bool gust=true,stop=false,finished=false,failed=false;
  int reset_count=0;
  int follow_carrier=-1;
  double visual_t=-1,accumulator=0;
  template<class T>T get(const std::shared_ptr<const sdf::Element>&s,const std::string &key,T fallback) {
    return s->HasElement(key)?s->Get<T>(key):fallback;
  }
  void initialise() {
    sim=std::make_unique<loop::Simulation>(loop::Config::load(params),mode=="central_local",gust);
    std::string folder=output+(reset_count?"/reset_"+std::to_string(reset_count):"");
    log=std::make_unique<loop::Log>(folder,"gazebo_live_reduced_model");log->record(*sim,true);
    finished=false;failed=false;visual_t=-1;accumulator=0;entities.clear();
  }
  void pose(gz::sim::EntityComponentManager &ecm,const std::string &name,loop::V3 p,const gz::math::Quaterniond &q={}) {
    auto it=entities.find(name);
    if(it==entities.end()) {
      auto e=ecm.EntityByComponents(gz::sim::components::Model(),gz::sim::components::Name(name));
      loop::require(e!=gz::sim::kNullEntity,"SDF model missing: "+name);it=entities.emplace(name,e).first;
    }
    gz::sim::Model(it->second).SetWorldPoseCmd(ecm,gz::math::Pose3d(gz::math::Vector3d(p.x,p.y,p.z),q));
  }
  void line(gz::sim::EntityComponentManager &ecm,const std::string &name,loop::V3 a,loop::V3 b) {
    auto d=b-a;double len=d.norm();loop::require(len>1e-8,"zero render segment");
    pose(ecm,name,(a+b)*.5,gz::math::Quaterniond(0,std::acos(std::clamp(d.z/len,-1.,1.)),std::atan2(d.y,d.x)));
  }
  void draw(gz::sim::EntityComponentManager &ecm) {
    const auto &c=sim->c;const auto &route=sim->route;
    for(size_t i=0;i<sim->carts.size();++i) {
      auto &a=sim->carts[i];auto d=route.tangent(sim->q+a.phase+a.offset);
      if(static_cast<int>(i)==follow_carrier) {
        // Fixed world offset avoids artificial camera roll during swing.
        pose(ecm,"inspection_camera_follow",a.pallet+loop::V3{2.4,-3.2,2.0},
             gz::math::Quaterniond(0,std::atan2(1.1,4.),std::atan2(3.2,-2.4)));
      }
      double yaw=std::atan2(d.y,d.x),pitch=-std::atan2(d.z,std::hypot(d.x,d.y));
      pose(ecm,"bogie_"+std::to_string(i),a.pivot+loop::V3{0,0,.11},gz::math::Quaterniond(0,pitch,yaw));
      auto rot=gz::math::Quaterniond(0,-a.tx,0)*gz::math::Quaterniond(a.ty,0,0)*gz::math::Quaterniond(0,0,yaw);
      pose(ecm,"pallet_"+std::to_string(i),a.pallet,rot);
      line(ecm,"hanger_"+std::to_string(i),a.pivot,a.pallet);
      auto tractor=route.at(sim->q+a.phase).p;
      pose(ecm,"coupler_"+std::to_string(i),(tractor+a.pivot)*.5+loop::V3{0,0,.8},gz::math::Quaterniond(0,pitch,yaw));
      for(int j=0;j<2;++j) {
        loop::V3 p{0,0,-50};
        if(a.payload>c.nominal_payload*(j+.15)/2) {
          auto shift=rot*gz::math::Vector3d(j? .27:-.27,0,.30);
          p=a.pallet+loop::V3{shift.X(),shift.Y(),shift.Z()};
        }
        pose(ecm,"load_"+std::to_string(i)+"_"+std::to_string(j),p,rot);
      }
    }
    for(int lane=0;lane<2;++lane)for(size_t k=0;k<route.spans[lane].size();++k) {
      const auto &s=route.spans[lane][k];std::vector<loop::V3> points;std::vector<double> arc{0};
      constexpr int fine=96;
      for(int i=0;i<=fine;++i){double x=s.x0+s.D()*i/fine;points.push_back({x,0,s.z(x)});
        if(i)arc.push_back(arc.back()+(points[i]-points[i-1]).norm());}
      auto at=[&](double u){double distance=u*arc.back();auto it=std::upper_bound(arc.begin(),arc.end(),distance);
        size_t j=std::min<size_t>(fine,std::max<size_t>(1,it-arc.begin()));double v=(distance-arc[j-1])/(arc[j]-arc[j-1]);
        return points[j-1]*(1-v)+points[j]*v;};
      for(int rail=0;rail<2;++rail)for(int j=0;j<c.cable_segments;++j) {
        auto a=at(double(j)/c.cable_segments),b=at(double(j+1)/c.cable_segments);
        a.y=b.y=(lane?c.lane_half_width:-c.lane_half_width)+(rail?c.gauge/2:-c.gauge/2);
        line(ecm,"flex_"+std::to_string(lane)+"_"+std::to_string(k)+"_"+std::to_string(rail)+"_"+std::to_string(j),a,b);
      }
    }
    pose(ecm,"main_rotor",{0,0,route.ground(0)+c.support_height+.8},gz::math::Quaterniond(0,0,-sim->q/c.lane_half_width));
    loop::V3 wp{0,0,-50};if(sim->wind>.05)wp={24,0,route.ground(24)+c.support_height+3};
    pose(ecm,"wind_indicator",wp,gz::math::Quaterniond(0,0,c.wind_bearing_deg*loop::pi/180));
    gz::msgs::StringMsg msg;std::ostringstream text;
    text<<"{\"model\":\"reduced_not_native_contact\",\"time_s\":"<<sim->t<<",\"stage\":"<<sim->stage<<",\"wind_m_s\":"<<sim->wind<<",\"line_speed_m_s\":"<<sim->v<<",\"main_force_N\":"<<sim->main_force<<"}";
    msg.set_data(text.str());status.Publish(msg);
  }
 public:
  ~LoopSystem() override {if(log&&sim&&!finished&&!failed){try{log->finish(*sim,"interrupted");}catch(...) {}}}
  void Configure(const gz::sim::Entity &,const std::shared_ptr<const sdf::Element> &s,
                 gz::sim::EntityComponentManager &,gz::sim::EventManager &manager) override {
    params=get<std::string>(s,"params","");output=get<std::string>(s,"output","results/loop");mode=get<std::string>(s,"mode","central_local");
    loop::require(mode=="central_only"||mode=="central_local","invalid control mode");
    gust=get<bool>(s,"gust",true);stop=get<bool>(s,"stop_at_end",false);events=&manager;
    follow_carrier=get<int>(s,"follow_carrier",-1);
    status=node.Advertise<gz::msgs::StringMsg>("/agro_loop/status");initialise();
  }
  void Reset(const gz::sim::UpdateInfo &,gz::sim::EntityComponentManager &) override {
    if(log&&sim&&!finished&&!failed) {log->finish(*sim,"reset_interrupted");}
    ++reset_count;initialise();
  }
  void PreUpdate(const gz::sim::UpdateInfo &info,gz::sim::EntityComponentManager &ecm) override {
    if(info.paused||failed||finished)return;
    try {
      double dt=std::chrono::duration<double>(info.dt).count();if(dt<=0)return;
      accumulator+=dt;
      // Fixed-step clock gives the same core trajectory as offline execution.
      while(accumulator>=sim->c.dt-1e-10&&!sim->complete) {sim->step(sim->c.dt);accumulator-=sim->c.dt;log->record(*sim);}
      if(sim->t-visual_t>=sim->c.visual_period-1e-8||sim->complete){draw(ecm);visual_t=sim->t;}
      if(sim->complete) {log->finish(*sim);finished=true;if(stop)events->Emit<gz::sim::events::Stop>();}
    }catch(const std::exception &e){gzerr<<"AgroLoopSystem: "<<e.what()<<std::endl;failed=true;
      if(log&&sim) {log->finish(*sim,"failed");}
      events->Emit<gz::sim::events::Stop>();}
  }
};
}
GZ_ADD_PLUGIN(agro::LoopSystem,gz::sim::System,agro::LoopSystem::ISystemConfigure,
              agro::LoopSystem::ISystemPreUpdate,agro::LoopSystem::ISystemReset)
