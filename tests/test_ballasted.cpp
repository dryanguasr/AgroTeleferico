#include "agro/loop.hpp"
#include <iostream>
using namespace agro::loop;
int main() {
 try {
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
