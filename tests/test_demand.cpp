#include "agro/demand.hpp"
#include <iostream>
#include <chrono>
using namespace agro::loop;
using namespace agro::demand;
Config configuration(){Config c;c.single_span=1;c.carriers_per_lane=1;c.terrain={{0,0},{8.6,3.2}};c.support_height=2.4;c.suspension=.48;c.lane_half_width=1.1;c.gauge=.42;
  c.bogie_mass=3;c.hanger_mass=.6;c.pallet_mass=1.4;c.nominal_payload=5;c.descending_payload=10;c.max_speed=.2;c.max_accel=.04;c.main_equivalent_mass=45;c.main_force_limit=600;
  c.coupling_k=1800;c.coupling_c=70;c.min_clearance=.4;c.station_start_offset=0;c.slack=.001;c.cable_EA=80000;c.max_tension=4000;c.guide_half_length=.6;c.guide_lift=.02;c.tractor_lift=.3;return c;}
void write(const std::filesystem::path &p,const std::string &text){std::ofstream f(p);f<<text;}
std::string read(const std::filesystem::path&p){std::ifstream f(p);return std::string(std::istreambuf_iterator<char>(f),{});}
int main(){try{
  auto root=std::filesystem::temp_directory_path()/("agro_demand_test_"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));std::filesystem::create_directories(root);
  Settings settings;require(settings.nextWindow(450,30)==450&&settings.nextWindow(451,30)==600&&settings.nextWindow(600,30)==600,"whole human operation must fit its operator window");
  bool reject=false;try{settings.nextWindow(0,481);}catch(...){reject=true;}require(reject,"operation exceeding an open window must be rejected");
  write(root/"settings.params","horizon_s 180\nmax_time_s 900\n");
  write(root/"orders.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\na,0,0,300,0,5,20,20\nb,0,100,400,1,5,20,20\n");
  {std::ofstream f(root/"predictor.csv");f<<"leg_kind,up_kg,down_kg,positive_J,absorbed_J,duration_s\n";
    for(std::string kind:{"first","upper0","lower0"})for(int u=0;u<=10;++u)for(int d=0;d<=10;++d)f<<kind<<','<<u<<','<<d<<','<<5+std::max(0,30*(u-d))<<','<<std::max(0,30*(d-u))<<','<<(kind=="first"?53.734:71.013)<<'\n';}
  writePredictorManifest((root/"predictor.csv").string(),configuration());
  require(agro::sha256("")=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","SHA256 empty vector");
  require(agro::sha256("abc")=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","SHA256 abc vector");
  require(agro::sha256(std::string(1000,'a'))=="41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3","SHA256 multiple blocks");
  auto rejects=[&](auto call,const std::string &why){bool caught=false;try{call();}catch(const std::exception&){caught=true;}require(caught,why);};
  auto table=(root/"predictor.csv").string();auto original=read(table+".manifest");
  rejects([&]{Config changed=configuration();changed.dt=.004;Predictor p;p.load(table,changed);},"dt mismatch accepted");
  rejects([&]{Config changed=configuration();changed.payload_ramp=3;Predictor p;p.load(table,changed);},"ramp mismatch accepted");
  rejects([&]{Config changed=configuration();changed.terrain[1].second+=.1;Predictor p;p.load(table,changed);},"geometry mismatch accepted");
  write(table+".manifest",original+"tamper");rejects([&]{Predictor p;p.load(table,configuration());},"manifest tamper accepted");
  auto wrongCore=original;wrongCore.replace(wrongCore.find("core_sha256 ")+12,64,std::string(64,'0'));
  write(table+".manifest",wrongCore);rejects([&]{Predictor p;p.load(table,configuration());},"wrong core accepted");
  write(table+".manifest",original);auto content=read(table);write(table,content+"\n");
  rejects([&]{Predictor p;p.load(table,configuration());},"table tamper accepted");write(table,content);
  std::filesystem::remove(table+".manifest");rejects([&]{Predictor p;p.load(table,configuration());},"legacy table accepted");write(table+".manifest",original);
  auto ramp=configuration();ramp.payload_ramp=4;ramp.initial_dwell=6;ramp.station_dwell=8;
  write(root/"ramp.csv",content);writePredictorManifest((root/"ramp.csv").string(),ramp);
  write(root/"short.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\nx,0,0,300,0,5,2,20\n");
  rejects([&]{Simulation sim(ramp,false,false);Engine e(sim,(root/"short.csv").string(),(root/"settings.params").string(),"A",(root/"ramp.csv").string(),(root/"rejected").string());},"short loading accepted");
  write(root/"short.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\nx,0,0,300,0,5,20,2\n");
  rejects([&]{Simulation sim(ramp,false,false);Engine e(sim,(root/"short.csv").string(),(root/"settings.params").string(),"A",(root/"ramp.csv").string(),(root/"rejected").string());},"short unloading accepted");
  write(root/"short_aux.params","horizon_s 180\nmax_time_s 900\nbuffer_setup_s 0\nbuffer_per_unit_s 2\n");
  rejects([&]{Simulation sim(ramp,false,false);Engine e(sim,(root/"orders.csv").string(),(root/"short_aux.params").string(),"C",(root/"ramp.csv").string(),(root/"rejected").string());},"short auxiliary handling accepted");
  require(!std::filesystem::exists(root/"rejected"),"invalid contract created service output");
  // Boundary: handling equals the configured ramp. Halfway mass is half the order.
  write(root/"ramp_order.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\nx,0,0,300,0,5,4,4\n");
  {Simulation sim(ramp,false,false);Engine e(sim,(root/"ramp_order.csv").string(),(root/"settings.params").string(),"A",(root/"ramp.csv").string(),(root/"ramp_run").string());
    while(sim.t<2-1e-8)sim.step(sim.c.dt);
    require(std::abs(sim.carts[0].payload-2.5)<.01,"configured ramp midpoint mismatch");
    while(!sim.complete)sim.step(sim.c.dt);
    e.finish();require(e.completed()&&e.loadedMass()==5&&e.unloadedMass()==5,"equal ramp service did not close");}

  Predictor pred;pred.load((root/"predictor.csv").string(),configuration());require(std::abs(pred.at("first",5.5,2.5).positive-95)<1e-10,"bilinear predictor interpolation");
  reject=false;try{pred.at("first",10.1,0);}catch(...){reject=true;}require(reject,"calibration bounds must not extrapolate");
  for(std::string policy:{"A","B","C","D"}){Simulation sim(configuration(),false,false);double energy0=sim.energy0;Engine engine(sim,(root/"orders.csv").string(),(root/"settings.params").string(),policy,(root/"predictor.csv").string(),(root/policy).string(),true);
    while(!sim.complete)sim.step(sim.c.dt);
    engine.finish();
    require(engine.completed()&&engine.isComparable(),"demand sequence must drain and close physically comparable: "+policy);
    require(std::abs(sim.energy()-energy0)<.1,"terminal reduced energy restored");
    require(std::abs(sim.q/sim.route.total-std::round(sim.q/sim.route.total))<.01,"terminal q at whole loop");
    require(engine.loadedMass()==10&&engine.unloadedMass()==10,"each useful load exactly once");
    for(const auto &a:sim.carts)require(a.payload==0,"empty carriers at terminal state");
    auto rows=read(root/policy/"orders.csv");require(rows.find(",4\n")!=std::string::npos,"delivered orders recorded");
    if(policy=="A"||policy=="B")require(read(root/policy/"demand_summary.json").find("\"buffer_moves_kg\":0")!=std::string::npos,"no auxiliary mass in baseline policies");
  }
  // Unknown future demand cannot affect a decision made before its announcement.
  write(root/"hidden.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\na,0,0,300,0,5,20,20\nb,100,100,400,1,5,20,20\n");
  write(root/"only.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\na,0,0,300,0,5,20,20\n");
  Simulation one(configuration(),false,false),two(configuration(),false,false);
  Engine e1(one,(root/"hidden.csv").string(),(root/"settings.params").string(),"C",(root/"predictor.csv").string(),(root/"hidden").string(),true);
  Engine e2(two,(root/"only.csv").string(),(root/"settings.params").string(),"C",(root/"predictor.csv").string(),(root/"only").string(),true);
  while(one.t<99){one.step(one.c.dt);two.step(two.c.dt);require(one.q==two.q&&one.drive_positive==two.drive_positive&&one.carts[0].payload==two.carts[0].payload&&one.carts[1].payload==two.carts[1].payload,"future announcement leaked into causal decisions");}
  write(root/"future_only.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\nf,0,100,400,1,5,20,20\n");
  {Simulation sim(configuration(),false,false);Engine engine(sim,(root/"future_only.csv").string(),(root/"settings.params").string(),"C",(root/"predictor.csv").string(),(root/"future_only").string(),true);
    while(sim.t<99)sim.step(sim.c.dt);
    require(std::abs(sim.q)<1e-9&&sim.carts[0].payload==0&&sim.carts[1].payload==0,"future goods alone must not cause a trip");}
  // A deliberately attractive auxiliary prediction must not delay a feasible
  // mandatory order. More than one module needs >10 s of simultaneous handling.
  {std::ofstream f(root/"deadline_predictor.csv");f<<"leg_kind,up_kg,down_kg,positive_J,absorbed_J,duration_s\n";
    for(std::string kind:{"first","upper0","lower0"})for(int u=0;u<=10;++u)for(int d=0;d<=10;++d)f<<kind<<','<<u<<','<<d<<','<<(kind=="first"?5+std::max(0,30*(u-d)):5)<<",0,"<<(kind=="first"?53.734:71.013)<<'\n';}
  writePredictorManifest((root/"deadline_predictor.csv").string(),configuration());
  write(root/"deadline.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\nurgent,0,0,75,0,5,10,10\noptional,0,100,400,1,5,80,10\n");
  {Simulation sim(configuration(),false,false);Engine engine(sim,(root/"deadline.csv").string(),(root/"settings.params").string(),"C",(root/"deadline_predictor.csv").string(),(root/"deadline").string(),true);
    while(sim.t<11)sim.step(sim.c.dt);
    require(sim.carts[1].payload<=1+1e-9,"auxiliary or early handling sacrificed a feasible deadline");
    require(sim.carts[0].payload==5&&sim.q>0,"urgent feasible service must depart promptly");}
  write(root/"empty.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\n");
  {Simulation sim(configuration(),false,false);Engine engine(sim,(root/"empty.csv").string(),(root/"settings.params").string(),"A",(root/"predictor.csv").string(),(root/"stop_counter").string(),true);
    sim.carts[0].stops=1; // Inject the observed diagnostic; do not pretend to validate its impulse physics.
    while(!sim.complete)sim.step(sim.c.dt);
    require(engine.completed()&&!engine.isComparable()&&engine.status()=="completed_noncomparable","a governor/stop intervention invalidates energy comparison");}
  auto runCase=[&](const std::string&name,const std::string&body,const std::string&policy,const std::string&prediction,double horizon=180){
    write(root/(name+".csv"),"id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\n"+body);
    write(root/(name+".params"),"horizon_s "+std::to_string(horizon)+"\nmax_time_s 1800\n");
    Simulation sim(configuration(),false,false);Engine engine(sim,(root/(name+".csv")).string(),(root/(name+".params")).string(),policy,(root/prediction).string(),(root/name).string(),true);
    while(!sim.complete)sim.step(sim.c.dt);
    engine.finish();
    require(engine.completed()&&engine.isComparable(),"edge case failed physical closure: "+name);
    return read(root/name/"demand_summary.json");};
  require(runCase("empty_closed","","A","predictor.csv").find("\"trips\":0")!=std::string::npos,"empty demand must not manufacture travel");
  runCase("only_up","u,0,0,500,0,5,20,20\n","A","predictor.csv");
  runCase("only_down","d,0,0,500,1,5,20,20\n","A","predictor.csv");
  require(runCase("impossible_deadline","late,0,0,1,0,5,20,20\n","A","predictor.csv").find("\"on_time_orders\":0")!=std::string::npos,"infeasible deadline must remain delivered and late");
  require(runCase("later_trip_deadline","a,0,0,300,0,8,20,20\nb,0,0,310,0,8,20,20\nc,0,0,330,0,8,20,20\n","B","predictor.csv").find("\"on_time_orders\":3")!=std::string::npos,
          "waiting must protect known work beyond the next two trips");
  runCase("wait_boundary","w,0,0,500,0,5,20,20\n","B","predictor.csv");
  {std::istringstream f(read(root/"wait_boundary"/"orders.csv"));std::string line;std::getline(f,line);std::getline(f,line);auto a=fields(line);double loading=number(a[8]);require(loading>=60&&loading<=60.0041,"bounded waiting must dispatch at exactly sixty seconds within one integration step");}
  runCase("window_boundary","w,470,470,1000,0,5,20,20\n","A","predictor.csv",500);
  {std::istringstream f(read(root/"window_boundary"/"orders.csv"));std::string line;std::getline(f,line);std::getline(f,line);auto a=fields(line);require(std::abs(number(a[8])-600)<.0041,"non-fitting operation must start at next operator opening");}
  auto exhausted=runCase("exhausted_aux","a,0,0,1500,0,10,20,20\nb,0,0,1500,0,10,20,20\n","C","deadline_predictor.csv");
  require(exhausted.find("\"orders_delivered\":2")!=std::string::npos,"exhausted auxiliary stock must not prevent useful delivery");
  {std::istringstream f(read(root/"exhausted_aux"/"demand_status.csv"));std::string line;std::getline(f,line);double minimum=10;while(std::getline(f,line)){auto a=fields(line);minimum=std::min(minimum,number(a[15]));require(number(a[14])>=-1e-8&&number(a[15])>=-1e-8,"auxiliary stock must not be fabricated or negative");}require(minimum<1e-8,"fixture must actually exhaust upper auxiliary inventory");}
  // Invalid rows are rejected before the engine can modify payload.
  write(root/"invalid.csv","id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\nx,0,0,10,0,11,20,20\n");
  reject=false;try{readOrders((root/"invalid.csv").string(),settings);}catch(...){reject=true;}require(reject,"overcapacity indivisible order must be rejected");
  std::cout<<"Demand policies, empty/directional/late demand, exhausted stocks, exact wait/window boundaries, causal input, mass/IDs, terminal closure and predictor bounds passed; evidence "<<root<<'\n';
 }catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}return 0;}
