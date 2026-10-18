// Quasistatic candidate screening using the SAME cable solver; not a simulation.
// Building fixed: edge x=8, top rail z=4.28, slab underside z=6.16.
#include "agro/loop.hpp"
#include <iostream>
#include <iomanip>
using namespace agro::loop;
int main(int argc,char **argv) {
 try {
  require(argc==2,"pass the archived two-floor loop.params");
  Config base=Config::load(argv[1]);
  std::cout<<std::setprecision(9)<<"span_m,head_m,suspension_m,slack,base_x_m,head_projection_m,tractor_lift_m,mast_extra_m,bar_margin_m,slab_margin_m,base_edge_margin_m,peak_cable_N,min_slide,min_overturn,candidate\n";
  for(double X:{8.6,8.8,9.0,9.2,9.4,9.5,10.})for(double h:{2.35,2.4,2.45})
  for(double suspension:{.48,.55})for(double slack:{.001,.002,.004,.008}) {
    Config c=base;c.terrain.back().first=X;c.support_height=h;c.suspension=suspension;c.slack=slack;
    double bx=X==9.2?2.2:X==9.4?2.6:2.8,lift=.35,mast_extra=.51;
    // A PROPOSED visible structural arm, never an invisible support or building anchor.
    // For these candidates the base stays at x=9.5 while its head projects toward the span.
    double projection=X<9.2?9.5-X:0;
    Route r(c);double minBar=1e9,peak=0,minSlide=1e9,minOver=1e9;
    // Hold both full payloads through the return: conservative loading compared
    // with the actual service, which unloads both at the end of its first leg.
    std::vector<double> masses{c.tare()+5,c.tare()+10};
    for(double q=0;q<=r.total;q+=.04) {
      std::vector<double> pos{q,q+r.lane_length+pi*c.lane_half_width};
      r.equilibrium(pos,masses);peak=std::max(peak,r.tensionMax());
      for(double s:pos) {auto p=r.at(s);
        if(std::abs(p.p.x-8)<.4)minBar=std::min(minBar,p.p.z-suspension-.1-4.28);
      }
      for(int end=0;end<2;++end) {
        double horizontal=0,vertical=0;
        for(auto &lane:r.spans) {auto &span=lane.front();horizontal+=2*span.H;vertical+=2*(end?span.rightReaction():span.leftReaction());}
        // Illustrative nominal bound, not all actuator saturation cases.
        double th=(2*c.tractor_pretension+200)/std::hypot(1.,3.2/X);
        double moment=horizontal*h+th*(h+lift);horizontal+=th;
        vertical+=(end?1:-1)*th*3.2/X;
        moment+=projection*std::abs(vertical);
        for(size_t j=0;j<pos.size();++j) {auto p=r.at(pos[j]);if((p.p.x<X/2?0:1)==end) {
          double w=masses[j]*g*(1-p.cable_weight);vertical+=w;moment+=w*(std::abs(p.p.x-(end?X:0))+projection);}}
        double normal=(c.station_dry_mass+c.ballast_litres*c.ballast_fill)*g+vertical;
        minSlide=std::min(minSlide,c.soil_mu*normal/horizontal);minOver=std::min(minOver,normal*bx/2/moment);
      }
    }
    double slab=6.16-(3.2+h+mast_extra),edge=X+projection-bx/2-8;
    bool candidate=minBar>=.05&&slab>=.049&&edge>=.099&&minSlide>=1&&minOver>=1;
    std::cout<<X<<','<<h<<','<<suspension<<','<<slack<<','<<bx<<','<<projection<<','<<lift<<','<<mast_extra<<','<<minBar<<','<<slab<<','<<edge<<','<<peak<<','<<minSlide<<','<<minOver<<','<<candidate<<'\n';
  }
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
