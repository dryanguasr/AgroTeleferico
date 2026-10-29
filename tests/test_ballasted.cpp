#include "agro/loop.hpp"
#include <iostream>
using namespace agro::loop;
void test_payload_energy() {
  // Isolate mass transfer from integration and cable-shape updates. Exercise
  // each carrier separately and both together so their errors cannot cancel.
  int cases=0;
  for(int serviced:{0,1,2})for(bool loading:{false,true})
  for(bool swing:{false,true})for(bool moving:{false,true}) {
    Config c;c.single_span=1;c.carriers_per_lane=1;c.terrain={{0,0},{8.6,3.2}};
    c.support_height=2.4;c.suspension=.48;c.lane_half_width=1.1;c.gauge=.42;
    c.bogie_mass=3;c.hanger_mass=.6;c.pallet_mass=1.4;
    c.nominal_payload=serviced==1?0:5;c.descending_payload=serviced==0?0:10;
    c.max_speed=.2;c.max_accel=.04;c.min_clearance=.4;c.station_start_offset=0;
    c.payload_ramp=2*c.dt;
    Simulation sim(c,false,false);
    sim.stage=loading?0:2;sim.q=loading?0:sim.route.lane_length;
    sim.t=loading?1:sim.topArrival()+1;sim.v=moving?.005:0;
    for(size_t j=0;j<sim.carts.size();++j) {
      auto &a=sim.carts[j];a.offset=j?-.02:.01;
      a.offset_speed=moving?(j?-.004:.003):0;
      a.payload=loading?0:(j?c.descending_payload:c.nominal_payload);
      a.tx=swing?(j?-.15:.2):0;a.ty=swing?(j?.12:-.1):0;
      a.wx=swing?(j?-.25:.3):0;a.wy=swing?(j?.35:-.2):0;
    }
    sim.updateShape();sim.refreshPositions();
    const double initial_energy=sim.energy(),initial_flux=sim.load_energy;
    for(int k=0;k<2;++k) {
      double before=sim.energy(),flux=sim.load_energy;
      sim.operation(c.dt);
      require(std::abs((sim.energy()-before)-(sim.load_energy-flux))<1e-10,
        "mass-transfer flux differs from reduced energy change at fixed state");
      sim.t+=c.dt;
    }
    require((loading?sim.load_status:sim.unload_status)==2,"mass transfer must complete");
    for(size_t j=0;j<sim.carts.size();++j)
      require(std::abs(sim.carts[j].payload-(loading?(j?c.descending_payload:c.nominal_payload):0))<1e-12,
        "both carriers must reach their requested payload");
    require(std::abs((sim.energy()-initial_energy)-(sim.load_energy-initial_flux))<1e-10,
      "total mass-transfer energy mismatch");
    require(loading?sim.load_energy>initial_flux:sim.load_energy<initial_flux,
      "loading and unloading must have opposite energy-flow signs");
    ++cases;
  }
  std::cout<<cases<<" frozen-state mass-transfer energy cases passed\n";
}
int main() {
 try {
  test_payload_energy();
  Config c;c.single_span=1;c.carriers_per_lane=1;c.terrain={{0,0},{8,0}};
  c.support_height=2.4;c.suspension=.55;c.lane_half_width=1.1;c.gauge=.42;
  c.bogie_mass=3;c.hanger_mass=.6;c.pallet_mass=1.4;c.nominal_payload=5;
  c.max_speed=.2;c.max_accel=.04;c.min_clearance=.4;
  Simulation s(c,false,false);
  require(s.carts.size()==2&&s.route.support_x.size()==2,"two carts, endpoints only");
  for(double u:{0.,s.route.lane_length,s.route.lane_length+pi*c.lane_half_width,s.route.total})
    require((s.route.at(u-1e-6).p-s.route.at(u+1e-6).p).norm()<1e-4,"return continuity");
  auto high=ballast(s,0);s.c.ballast_fill=.2;auto low=ballast(s,0);
  require(high.water_kg==480&&low.water_kg==120,"litres to kg");
  require(high.cg_z>low.cg_z&&high.sliding_margin>low.sliding_margin&&high.overturn_margin>low.overturn_margin,"fill changes mass, CG and stability");
  for(auto &lane:s.route.spans) for(auto &span:lane) {
    auto length=span.L0;span.solve({});auto sag=span.sag;span.solve({{4,75}});
    require(span.L0==length&&span.sag>sag,"moving load changes sag without retensioning");
    double previous=0;
    for(double payload:{0.,5.,10.}) {
      span.solve({{4,(c.tare()+payload)*g/2}});
      require(span.sag>previous,"0/5/10 kg must increase sag");previous=span.sag;
    }
  }
  Config bad=c;bad.ballast_fill=1.1;bool rejected=false;
  try {bad.validate();} catch(...) {rejected=true;}require(rejected,"invalid filling rejected");
  std::cout<<"Two-carrier topology, continuity, fixed length, mass/CG/stability and domain checks passed\n";
 } catch(const std::exception&e) {std::cerr<<e.what()<<'\n';return 1;}
}
