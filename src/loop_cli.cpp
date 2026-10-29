#include "agro/loop_log.hpp"
#include "agro/demand.hpp"
#include <iostream>
#include <memory>
// Static screening only; not a proof of support strength or dynamic feasibility.
static void screenSupports(agro::loop::Config cfg,const std::string &output) {
  using namespace agro::loop;
  require(!std::filesystem::exists(output),"screening output already exists");
  std::filesystem::create_directories(output);std::ofstream f(std::filesystem::path(output)/"supports.json");
  require(bool(f),"cannot open support report");f<<std::setprecision(12)<<"{\n  \"origin\": \"static_reduced_model_screening\",\n  \"candidates\": [";
  bool first=true;
  for(int n:{3,4,5}) {cfg.supports_per_segment=n;Route route(cfg);double tension=0,sag=0,clearance=1e9;int negative=0;
    for(auto span:route.spans[0]) {
      // Isolated stress case: two fully loaded carriers in EACH span separately.
      double P=(cfg.tare()+cfg.nominal_payload)*g*.5;
      span.solve({{span.D()/3,P},{2*span.D()/3,P}});
      tension=std::max(tension,span.maxT);sag=std::max(sag,span.sag);
      negative+=span.leftReaction()<0;negative+=span.rightReaction()<0;
      for(int j=0;j<=100;++j) {double x=span.x0+span.D()*j/100.;
        clearance=std::min(clearance,span.z(x)-cfg.suspension-.2-route.ground(x));}
    }
    if(!first) {f<<",";}
    first=false;
    f<<"\n    {\"supports_per_segment\":"<<n<<",\"unique_portals\":"<<route.support_x.size()
     <<",\"peak_tension_N\":"<<tension<<",\"max_sag_m\":"<<sag<<",\"min_nominal_clearance_m\":"<<clearance
     <<",\"negative_vertical_end_reactions\":"<<negative<<"}";
  }
  f<<"\n  ],\n  \"assumptions\": \"two full carriers per span tested separately; symmetric portantes; fixed natural lengths; retained supports; no structural rating or wind\"\n}\n";
}
int main(int argc,char **argv) {
  std::unique_ptr<agro::loop::Simulation> s;std::unique_ptr<agro::loop::Log> log;
  std::unique_ptr<agro::demand::Engine> demand_engine;
  try {
    std::string config,output,mode="central_local",demand,dispatch,policy="A",predictor;
    bool wind=true,screen=false,compact=false,calibrate=false;double until=0;
    for(int i=1;i<argc;++i) {std::string a=argv[i];
      if(a=="--no-wind"){wind=false;continue;}
      if(a=="--screen-supports"){screen=true;continue;}
      if(a=="--compact"){compact=true;continue;}
      if(a=="--build-predictor"){calibrate=true;continue;}
      if(a=="--help"){std::cout<<"agro_loop_cli --config generated.params --output NEW_DIR [--mode central_only|central_local] [--no-wind] [--until seconds] [--screen-supports]\n"
        <<"Demand: --demand orders.csv --dispatch-config scenario.params --policy A|B|C|D --predictor predictor.csv [--compact]\n"
        <<"Calibration: --build-predictor (writes the complete 363-cell predictor.csv)\n";return 0;}
      agro::loop::require(i+1<argc,"missing argument for "+a);std::string b=argv[++i];
      if(a=="--config")config=b;else if(a=="--output")output=b;else if(a=="--mode")mode=b;else if(a=="--until")until=std::stod(b);
      else if(a=="--demand")demand=b;else if(a=="--dispatch-config")dispatch=b;else if(a=="--policy")policy=b;else if(a=="--predictor")predictor=b;
      else throw std::runtime_error("unknown option: "+a);}
    agro::loop::require(!config.empty()&&!output.empty(),"--config and --output are required");
    agro::loop::require(mode=="central_only"||mode=="central_local","invalid mode");
    agro::loop::require(std::isfinite(until)&&until>=0,"invalid --until");
    if(screen){screenSupports(agro::loop::Config::load(config),output);return 0;}
    if(calibrate){agro::loop::require(demand.empty(),"predictor calibration does not accept demand");agro::demand::buildPredictor(agro::loop::Config::load(config),output);return 0;}
    s=std::make_unique<agro::loop::Simulation>(agro::loop::Config::load(config),mode=="central_local",wind);
    log=std::make_unique<agro::loop::Log>(output,"standalone_reduced_model");
    if(!demand.empty())demand_engine=std::make_unique<agro::demand::Engine>(*s,demand,dispatch,policy,predictor,output,compact);
    log->record(*s,true);
    while(!s->complete&&(!until||s->t<until)) {s->step(s->c.dt);if(!compact)log->record(*s);}
    if(demand_engine){demand_engine->finish();log->finish(*s,s->complete?demand_engine->status():"partial_requested");}
    else log->finish(*s,s->complete?"completed":"partial_requested");
    std::cout<<"time="<<s->t<<" q="<<s->q<<"/"<<s->route.total<<" tension="<<s->peak_tension<<" swing="<<s->peak_swing<<" residual_J="<<s->residual()<<'\n';
    return demand_engine&&s->complete?(demand_engine->completed()?(demand_engine->isComparable()?0:2):1):0;
  }catch(const std::exception &e){if(demand_engine)demand_engine->finish("failed");if(log&&s)log->finish(*s,"failed");std::cerr<<"ERROR at t="<<(s?s->t:0)<<": "<<e.what()<<'\n';return 1;}
}
