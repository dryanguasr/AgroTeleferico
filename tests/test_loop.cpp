#include "agro/loop.hpp"
#include <iostream>
using namespace agro::loop;
int main() {
 try {
  Config c;Route r(c);
  require(r.support_x.size()==13,"13 unique towers for four inclusive per segment");
  require(r.ground(12)>r.ground(0)&&r.ground(36)>r.ground(12)&&r.ground(24)<r.ground(12),"extrema");
  for(double s:{0.,r.lane_length,r.lane_length+pi*c.lane_half_width,2*r.lane_length+pi*c.lane_half_width,r.total})
    require((r.at(s-.00001).p-r.at(s+.00001).p).norm()<.0001,"closed route continuous");
  Span p(0,4,6,8,c);p.solve({});double sag=p.sag,T=p.maxT,L=p.L0;
  p.solve({{2,100}});require(p.sag>sag&&p.maxT>T&&p.L0==L,"load changes shape without retensioning");
  p.solve({{1,80},{3,120}});
  require(std::abs(p.leftReaction()+p.rightReaction()-p.w*4-200)<1e-8,"reactions balance");
  require(std::abs(p.z(0)-6)<1e-8&&std::abs(p.z(4)-8)<1e-8,"cable endpoints");
  require(std::abs(p.naturalLength(p.H)-L)<1e-7,"fixed natural length");
  Simulation sim(c,true,true);
  for(int i=0;i<1000;++i)sim.step(c.dt);
  require(sim.carts.size()==6&&sim.q<.01,"six carts and initial dwell");
  Config bad=c;bad.terrain[3].second=3;bool rejected=false;
  try{bad.validate();}catch(const std::exception&){rejected=true;}require(rejected,"bad extrema rejected");
  std::cout<<"Loop core assertions passed: geometry, closure, loading, reactions, compatibility, IDs, dwell, config.\n";
 } catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
}
