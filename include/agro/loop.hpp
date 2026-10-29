#pragma once
// Conceptual reduced-order loop. Standard C++17; shared by Gazebo and offline tests.
// No native wheel/cable contact, distributed cable vibration, or electrical recovery.
#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <limits>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace agro::loop {
constexpr double pi = 3.14159265358979323846, g = 9.81;
struct V3 {
  double x=0,y=0,z=0;
  V3 operator+(V3 b) const {return {x+b.x,y+b.y,z+b.z};}
  V3 operator-(V3 b) const {return {x-b.x,y-b.y,z-b.z};}
  V3 operator*(double k) const {return {x*k,y*k,z*k};}
  V3 operator/(double k) const {return *this*(1/k);}
  double dot(V3 b) const {return x*b.x+y*b.y+z*b.z;}
  double norm() const {return std::sqrt(dot(*this));}
};
inline double sq(double x) {return x*x;}
inline double smooth(double u) {u=std::clamp(u,0.,1.);return u*u*u*(10+u*(-15+6*u));}
inline double wrap(double s,double L) {s=std::fmod(s,L);return s<0?s+L:s;}
inline void require(bool yes,const std::string &why) {if(!yes) throw std::runtime_error(why);}

struct Config {
  int single_span=0;
  double descending_payload=10;
  double tractor_lift=.8,base_offset=0;
  double ballast_litres=600,ballast_fill=.8,station_dry_mass=85,base_x=2.8,base_y=3.3;
  double soil_mu=.55,tractor_pretension=100,tank_bottom=.22,tank_height=1,dry_cg_z=.8;
  int carriers_per_lane=3, supports_per_segment=4, cable_segments=12;
  double dt=.002, shape_period=.02, log_period=.05, visual_period=.05;
  double support_height=6, lane_half_width=2, gauge=.8, guide_half_length=.8;
  double guide_lift=.04, slack=.006, cable_EA=180000, cable_kg_per_horizontal_m=.15;
  double bogie_mass=8, hanger_mass=2, pallet_mass=5, nominal_payload=20, suspension=1;
  double max_speed=.4, max_accel=.10, main_equivalent_mass=400, main_force_limit=2500;
  double drive_radius=.3, rolling_coefficient=1.2, main_drag=2;
  double coupling_k=3500, coupling_c=140, local_stroke=.22, local_speed=.18;
  double local_force_limit=60, local_damping_gain=25, swing_damping=.7;
  double air_density=1.15, drag_coefficient=1.1, area_empty=.3, area_per_kg=.012;
  double wind_speed=4, wind_duration=10, wind_bearing_deg=65;
  double max_tension=6000, min_clearance=1, max_swing=.35;
  double station_start_offset=.05, derivative_step=.03;
  double initial_dwell=5, station_dwell=7, final_dwell=8, station_tolerance=.09;
  double stop_speed=.012, payload_ramp=2, profile_dx=.025;
  std::vector<std::pair<double,double>> terrain{{0,0},{12,6},{24,1},{36,9},{48,3}};
  double tare() const {return bogie_mass+hanger_mass+pallet_mass;}
  void validate() const {
    require(carriers_per_lane>=1&&carriers_per_lane<=12,"carriers_per_lane outside [1,12]");
    require(supports_per_segment>=3&&supports_per_segment<=8,"supports_per_segment outside [3,8]");
    require(cable_segments>=6&&cable_segments<=48,"cable_segments outside [6,48]");
    require(single_span==0||single_span==1,"invalid topology selector");
    require(terrain.size()==(single_span?2:5),"terrain count incompatible with topology");
    if(single_span) require(carriers_per_lane==1&&descending_payload>=0,"single span needs two carriers and nonnegative descending load");
    if(single_span) {
      require(std::isfinite(tractor_lift)&&tractor_lift>=.3&&std::isfinite(base_offset)&&base_offset>=0,"invalid tractor/base geometry");
      for(double v:{ballast_litres,station_dry_mass,base_x,base_y,soil_mu,tractor_pretension,tank_height,dry_cg_z})
        require(std::isfinite(v)&&v>0,"invalid ballast/station parameter");
      require(std::isfinite(ballast_fill)&&ballast_fill>=0&&ballast_fill<=1&&tank_bottom>=0,"invalid filling/tank level");
    }
    for(size_t i=0;i<terrain.size();++i) {
      require(std::isfinite(terrain[i].first)&&std::isfinite(terrain[i].second),"nonfinite terrain");
      if(i) require(terrain[i].first>terrain[i-1].first,"terrain x must increase");
    }
    require(terrain.front().first==0,"terrain must start at x=0");
    if(!single_span) require(terrain[1].second>terrain[0].second&&terrain[1].second>terrain[2].second&&
      terrain[3].second>terrain[2].second&&terrain[3].second>terrain[4].second&&
      terrain[3].second>terrain[1].second&&terrain[4].second>terrain[0].second,"invalid terrain extrema");
    for(double v:{dt,shape_period,log_period,visual_period,support_height,lane_half_width,gauge,
      guide_half_length,slack,cable_EA,cable_kg_per_horizontal_m,bogie_mass,pallet_mass,suspension,
      max_speed,max_accel,main_equivalent_mass,main_force_limit,drive_radius,coupling_k,coupling_c,
      local_stroke,local_speed,local_force_limit,air_density,wind_duration,profile_dx,payload_ramp})
      require(std::isfinite(v)&&v>0,"invalid positive configuration value");
    for(double v:{guide_lift,hanger_mass,nominal_payload,rolling_coefficient,main_drag,local_damping_gain,
      swing_damping,drag_coefficient,area_empty,area_per_kg,wind_speed,initial_dwell,station_dwell,final_dwell})
      require(std::isfinite(v)&&v>=0,"invalid nonnegative configuration value");
    require(dt<=.01&&shape_period>=dt&&log_period>=dt&&visual_period>=dt,"invalid integration rates");
    require(slack<.05&&gauge<lane_half_width&&max_swing>0&&max_swing<.6,"invalid geometric domain");
    require(max_tension>0&&min_clearance>0&&stop_speed>0&&station_tolerance>local_stroke/3,
      "invalid acceptance limits");
    require(initial_dwell>payload_ramp+1&&station_dwell>payload_ramp+2,"dwell too short for loading");
    require(profile_dx<=.1&&derivative_step>0&&derivative_step<=.1,"reference/differential resolution outside domain");
    require(station_start_offset>=0&&station_start_offset<station_tolerance*.8,"invalid station starting offset");
  }
  // A generated SI key/value interchange file, not a second user configuration format.
  static Config load(const std::string &path) {
    std::ifstream f(path);require(bool(f),"cannot open config: "+path);Config c;
    std::string key;double v;
    while(f>>key) {
      if(key[0]=='#') {std::string tail;std::getline(f,tail);continue;}
      if(key=="terrain") {int n=0;require(bool(f>>n)&&(n==2||n==5),"invalid terrain count");c.terrain.clear();
        for(int i=0;i<n;++i) {double x=0,z=0;require(bool(f>>x>>z),"invalid terrain point");c.terrain.emplace_back(x,z);}continue;}
      require(bool(f>>v)&&std::isfinite(v),"invalid config value for "+key);
#define P(name) if(key==#name) {c.name=v;continue;}
#define I(name) if(key==#name) {require(v==std::floor(v),"integer expected: "+key);c.name=int(v);continue;}
      I(single_span) P(descending_payload) I(carriers_per_lane) I(supports_per_segment) I(cable_segments)
      P(tractor_lift) P(base_offset)
      P(ballast_litres) P(ballast_fill) P(station_dry_mass) P(base_x) P(base_y)
      P(soil_mu) P(tractor_pretension) P(tank_bottom) P(tank_height) P(dry_cg_z)
      P(dt) P(shape_period) P(log_period) P(visual_period) P(support_height) P(lane_half_width) P(gauge)
      P(guide_half_length) P(guide_lift) P(slack) P(cable_EA) P(cable_kg_per_horizontal_m)
      P(bogie_mass) P(hanger_mass) P(pallet_mass) P(nominal_payload) P(suspension)
      P(max_speed) P(max_accel) P(main_equivalent_mass) P(main_force_limit) P(drive_radius)
      P(rolling_coefficient) P(main_drag) P(coupling_k) P(coupling_c) P(local_stroke) P(local_speed)
      P(local_force_limit) P(local_damping_gain) P(swing_damping) P(air_density) P(drag_coefficient)
      P(area_empty) P(area_per_kg) P(wind_speed) P(wind_duration) P(wind_bearing_deg)
      P(max_tension) P(min_clearance) P(max_swing) P(initial_dwell) P(station_dwell) P(final_dwell)
      P(station_tolerance) P(stop_speed) P(payload_ramp) P(profile_dx) P(station_start_offset) P(derivative_step)
#undef P
#undef I
      throw std::runtime_error("unknown config key: "+key);
    }
    require(f.eof(),"malformed configuration");c.validate();return c;
  }
};

// Vertical equilibrium under uniform load per horizontal metre and point weights.
// z''=w/H with jumps P/H; elastic compatibility is integrated, not retensioned.
struct PointLoad {double x,weight;};
class Span {
 public:
  double x0,x1,z0,z1,L0,w,EA,H=1,V0=0,maxT=0,sag=0,elastic=0,potential=0;
  std::vector<PointLoad> loads;
  Span(double a,double b,double za,double zb,const Config &c):x0(a),x1(b),z0(za),z1(zb),
    L0(std::hypot(b-a,zb-za)*(1+c.slack)),w(c.cable_kg_per_horizontal_m*g),EA(c.cable_EA) {}
  double D() const {return x1-x0;}
  double startV(double h) const {
    double r=h*(z1-z0)/D()-w*D()/2;
    for(auto p:loads) r-=p.weight*(D()-p.x)/D();
    return r;
  }
  double z(double x) const {
    double a=std::clamp(x-x0,0.,D());
    double v=z0+(V0*a+.5*w*a*a)/H;
    for(auto p:loads) v+=p.weight*std::max(0.,a-p.x)/H;
    return v;
  }
  double slope(double x) const {
    double a=std::clamp(x-x0,0.,D()),v=V0+w*a;
    for(auto p:loads) if(a>=p.x) v+=p.weight;
    return v/H;
  }
  template<class F> double integrate(F fun) const {
    static constexpr double a[4]={.1834346424956498,.5255324099163290,.7966664774136267,.9602898564975363};
    static constexpr double wt[4]={.3626837833783620,.3137066458778873,.2223810344533745,.1012285362903763};
    std::vector<double> ends{0};for(auto p:loads) if(p.x>0&&p.x<D()) ends.push_back(p.x);ends.push_back(D());
    std::sort(ends.begin(),ends.end());double sum=0;
    for(size_t j=1;j<ends.size();++j) {double m=(ends[j]+ends[j-1])/2,h=(ends[j]-ends[j-1])/2;
      for(int k=0;k<4;++k) sum+=wt[k]*h*(fun(m-h*a[k])+fun(m+h*a[k]));}
    return sum;
  }
  double naturalLength(double h) const {
    double v0=startV(h);
    return integrate([&](double a) {double v=v0+w*a;for(auto p:loads) if(a>=p.x) v+=p.weight;
      double T=std::hypot(h,v);return (T/h)/(1+T/EA);});
  }
  void solve(std::vector<PointLoad> p,bool diagnostics=true) {
    for(auto v:p) require(v.x>=0&&v.x<=D()&&v.weight>=0&&std::isfinite(v.weight),"invalid point load");
    loads=std::move(p);double lo=.001,hi=100;
    while(naturalLength(hi)>L0&&hi<1e9) hi*=2;
    require(naturalLength(lo)>L0&&naturalLength(hi)<L0,"elastic cable root not bracketed");
    for(int k=0;k<48;++k) {double m=(lo+hi)/2;if(naturalLength(m)>L0)lo=m;else hi=m;}
    H=(lo+hi)/2;V0=startV(H);double end=V0+w*D();for(auto v:loads)end+=v.weight;
    maxT=std::max(std::hypot(H,V0),std::hypot(H,end));
    if(!diagnostics)return;
    sag=0;
    for(int i=0;i<=64;++i) {double a=D()*i/64.;sag=std::max(sag,z0+(z1-z0)*a/D()-z(x0+a));}
    elastic=integrate([&](double a){double T=H*std::hypot(1.,slope(x0+a));
      return T*T/(2*EA)*std::hypot(1.,slope(x0+a))/(1+T/EA);});
    potential=integrate([&](double a){return w*z(x0+a);});
    require(std::abs(naturalLength(H)-L0)<1e-7,"cable length residual");
  }
  double leftReaction() const {return -V0;}
  double rightReaction() const {double r=V0+w*D();for(auto p:loads)r+=p.weight;return r;}
};

struct RoutePoint {V3 p;int lane=-1,span=-1;double cable_weight=0;};
class Route {
 public:
  Config c;std::vector<double> support_x,arc_x,arc_s;double lane_length=0,total=0;
  std::array<std::vector<Span>,2> spans;
  explicit Route(Config cfg):c(std::move(cfg)) {
    c.validate();
    if(c.single_span) support_x.push_back(c.terrain.front().first);
    else for(int j=0;j<4;++j)for(int k=0;k<c.supports_per_segment-1;++k)
      support_x.push_back(c.terrain[j].first+(c.terrain[j+1].first-c.terrain[j].first)*k/(c.supports_per_segment-1));
    support_x.push_back(c.terrain.back().first);
    for(int lane=0;lane<2;++lane)for(size_t i=1;i<support_x.size();++i) {
      spans[lane].emplace_back(support_x[i-1],support_x[i],ground(support_x[i-1])+c.support_height,
        ground(support_x[i])+c.support_height,c);spans[lane].back().solve({});}
    int n=int(std::ceil(c.terrain.back().first/c.profile_dx));
    for(int k=0;k<=n;++k) {double x=c.terrain.back().first*k/n;arc_x.push_back(x);
      if(k)lane_length+=std::hypot(x-arc_x[k-1],ground(x)-ground(arc_x[k-1]));
      arc_s.push_back(lane_length);}
    total=2*lane_length+2*pi*c.lane_half_width;
    require(total/(2*c.carriers_per_lane)>2.5,"carrier spacing insufficient for nominal pallet");
    for(size_t i=1;i<support_x.size();++i)require(support_x[i]-support_x[i-1]>2*c.guide_half_length,"overlapping guides");
  }
  double ground(double x) const {
    if(x<=c.terrain.front().first)return c.terrain.front().second;
    if(x>=c.terrain.back().first)return c.terrain.back().second;
    for(size_t j=1;j<c.terrain.size();++j)if(x<=c.terrain[j].first) {
      auto a=c.terrain[j-1],b=c.terrain[j];double u=(x-a.first)/(b.first-a.first);
      return a.second+(b.second-a.second)*(c.single_span?u:(.5-.5*std::cos(pi*u)));}
    throw std::runtime_error("unreachable terrain interval");
  }
  double xFromArc(double s) const {
    s=std::clamp(s,0.,lane_length);auto it=std::upper_bound(arc_s.begin(),arc_s.end(),s);
    size_t j=std::min<size_t>(arc_s.size()-1,std::max<size_t>(1,it-arc_s.begin()));
    double u=(s-arc_s[j-1])/(arc_s[j]-arc_s[j-1]);return arc_x[j-1]*(1-u)+arc_x[j]*u;
  }
  double guideZ(double x) const {
    if(!c.single_span)return ground(x)+c.support_height+c.guide_lift;
    double X=c.terrain.back().first,slope=(c.terrain.back().second-c.terrain.front().second)/X;
    double d=std::min(x,X-x),u=std::clamp(d/c.guide_half_length,0.,1.);
    double rise=c.guide_half_length*(2*u*u-u*u*u)*slope;
    if(d<c.guide_half_length)return (x<X/2?c.terrain.front().second+rise:c.terrain.back().second-rise)+c.support_height+c.guide_lift;
    return ground(x)+c.support_height+c.guide_lift;
  }
  RoutePoint at(double s) const {
    s=wrap(s,total);double L=lane_length,r=c.lane_half_width,X=c.terrain.back().first;
    if(s<=L||(s>=L+pi*r&&s<=2*L+pi*r)) {
      int lane=s<=L?0:1;double x=xFromArc(lane==0?s:2*L+pi*r-s);
      auto it=std::upper_bound(support_x.begin(),support_x.end(),x);
      int i=int(std::min<size_t>(support_x.size()-2,std::max<size_t>(1,it-support_x.begin())-1));
      double d=std::min(std::abs(x-support_x[i]),std::abs(x-support_x[i+1]));
      double wgt=smooth(d/c.guide_half_length);
      double z=(1-wgt)*guideZ(x)+wgt*spans[lane][i].z(x);
      return {{x,lane==0?-r:r,z},lane,i,wgt};
    }
    if(s<L+pi*r) {double a=-pi/2+(s-L)/r;
      return {{X+r*std::cos(a),r*std::sin(a),ground(X)+c.support_height+c.guide_lift},-1,-1,0};}
    double a=pi/2+(s-2*L-pi*r)/r;
    return {{r*std::cos(a),r*std::sin(a),ground(0)+c.support_height+c.guide_lift},-2,-1,0};
  }
  V3 tangent(double s) const {constexpr double e=.004;return (at(s+e).p-at(s-e).p)/(2*e);}
  V3 curvature(double s) const {constexpr double e=.015;return (at(s+e).p+at(s-e).p-at(s).p*2)/(e*e);}
  // Differentiate the equilibrium FAMILY as the carrier moves, not the kink in a
  // fixed cable at a point load. The latter produces a fictitious impulsive curvature.
  V3 movedLoadPoint(size_t id,double s,const std::vector<double> &positions,const std::vector<double> &masses) const {
    auto p=at(s);if(p.lane<0||p.cable_weight<1e-10)return p.p;
    Span span=spans[p.lane][p.span];std::vector<PointLoad> loads;
    for(size_t j=0;j<positions.size();++j) {auto a=at(j==id?s:positions[j]);
      if(a.lane==p.lane&&a.span==p.span&&a.cable_weight>1e-10)
        loads.push_back({a.p.x-span.x0,masses[j]*g*.5*a.cable_weight});}
    span.solve(std::move(loads),false);
    p.p.z=(1-p.cable_weight)*guideZ(p.p.x)+p.cable_weight*span.z(p.p.x);
    return p.p;
  }
  void equilibrium(const std::vector<double> &positions,const std::vector<double> &masses) {
    require(positions.size()==masses.size(),"positions/masses mismatch");
    std::array<std::vector<std::vector<PointLoad>>,2> loads;
    for(auto &l:loads)l.resize(support_x.size()-1);
    for(size_t j=0;j<positions.size();++j) {auto p=at(positions[j]);if(p.lane>=0&&p.cable_weight>1e-9)
      loads[p.lane][p.span].push_back({p.p.x-support_x[p.span],masses[j]*g*.5*p.cable_weight});}
    for(int lane=0;lane<2;++lane)for(size_t j=0;j<spans[lane].size();++j)spans[lane][j].solve(std::move(loads[lane][j]));
  }
  double cableEnergy() const {double e=0;for(auto &l:spans)for(auto &s:l)e+=2*(s.elastic+s.potential);return e;}
  double tensionMax() const {double t=0;for(auto &l:spans)for(auto &s:l)t=std::max(t,s.maxT);return t;}
  double sagMax() const {double t=0;for(auto &l:spans)for(auto &s:l)t=std::max(t,s.sag);return t;}
};

struct Motion {double s=0,v=0,a=0;};
class Simulation;
// Optional causal service controller. The legacy scripted run remains the default.
// The controller owns scheduling only; all motion and energy remain integrated here.
struct Program {
  virtual ~Program()=default;
  virtual Motion reference(double time) const=0;
  virtual double duration() const=0;
  virtual void beforeStep(Simulation &,double)=0;
  virtual void afterStep(Simulation &)=0;
  virtual double loadedMass() const {return 0;}
  virtual double unloadedMass() const {return 0;}
};
struct Leg {
  double distance,speed,tau,cruise,duration;
  Leg(double d,const Config &c):distance(d),speed(c.max_speed) {
    tau=pi*speed/(2*c.max_accel);
    if(d<speed*tau) {speed=std::sqrt(d*2*c.max_accel/pi);tau=pi*speed/(2*c.max_accel);}
    cruise=std::max(0.,d/speed-tau);duration=2*tau+cruise;
  }
  Motion at(double t) const {
    if(t<=0)return {};
    if(t>=duration)return {distance,0,0};
    auto up=[&](double u){return Motion{speed/2*(u-tau/pi*std::sin(pi*u/tau)),
      speed/2*(1-std::cos(pi*u/tau)),speed*pi/(2*tau)*std::sin(pi*u/tau)};};
    if(t<tau)return up(t);
    if(t<tau+cruise)return {speed*tau/2+speed*(t-tau),speed,0};
    auto end=up(duration-t);return {distance-end.s,end.v,-end.a};
  }
};
struct Carrier {
  double phase=0,offset=0,offset_speed=0,payload=0,tx=0,ty=0,wx=0,wy=0;
  double connector=0,local_force=0,saturation=0,stops=0;
  V3 pivot,pallet,velocity,wind_force;
};
struct Event {double time;std::string name;int carrier;double from,to;};
class Simulation {
 public:
  Config c;Route route;Leg first,second;std::vector<Carrier> carts;std::vector<Event> events;
  bool hybrid=true,gust=true,complete=false;double t=0,q=0,v=0,main_force=0,wind=0;
  double drive_work=0,local_work=0,wind_work=0,loss_work=0,load_energy=0,stop_loss=0;
  double drive_positive=0,drive_absorbed=0,local_positive=0,local_absorbed=0,energy0=0;
  double last_shape=-1,peak_force=0,peak_local=0,peak_swing=0,peak_tension=0,min_gap=1e9;
  double min_ground=1e9,local_peak_offset=0,local_peak_speed=0,max_step_displacement=0;
  double max_reference_error=0,wind_on=-1,wind_end=-1;
  bool gust_end_recorded=false;
  int stage=0,load_status=0,unload_status=0;double operation_start=-1;
  std::vector<V3> path_d,path_dd;
  Program *program=nullptr; // non-owning; callers keep the program alive past Simulation
  Simulation(Config cfg,bool use_local=true,bool use_gust=true):c(std::move(cfg)),route(c),
    first(route.lane_length,c),second(route.total-route.lane_length,c),hybrid(use_local),gust(use_gust) {
    for(int lane=0;lane<2;++lane)for(int j=0;j<c.carriers_per_lane;++j) {
      Carrier a;a.phase=(lane?route.lane_length+pi*c.lane_half_width:0)+route.lane_length*j/c.carriers_per_lane+c.station_start_offset;
      a.payload=c.single_span?0:(lane?c.nominal_payload*(j%2? .5:1):0);carts.push_back(a);}
    updateShape();
    // Initialise passive couplings near loaded equilibrium; do not start with six
    // artificially released springs. This is an initial condition, not a reset in motion.
    for(int it=0;it<24;++it) {
      for(size_t j=0;j<carts.size();++j) {
        double target=-(c.tare()+carts[j].payload)*g*path_d[j].z/c.coupling_k;
        require(std::abs(target)<c.local_stroke,"initial coupling equilibrium exceeds stroke");
        carts[j].offset=.5*carts[j].offset+.5*target;
      }
      updateShape();
    }
    refreshPositions();energy0=energy();
  }
  double topArrival() const {return c.initial_dwell+first.duration;}
  double secondStart() const {return topArrival()+c.station_dwell;}
  double finalArrival() const {return secondStart()+second.duration;}
  double duration() const {return program?program->duration():finalArrival()+c.final_dwell;}
  Motion reference(double time) const {
    if(program)return program->reference(time);
    if(time<c.initial_dwell)return {};
    if(time<topArrival())return first.at(time-c.initial_dwell);
    if(time<secondStart())return {route.lane_length,0,0};
    if(time<finalArrival()) {auto a=second.at(time-secondStart());a.s+=route.lane_length;return a;}
    return {route.total,0,0};
  }
  int stageAt(double time) const {return time<c.initial_dwell?0:time<topArrival()?1:time<secondStart()?2:time<finalArrival()?3:4;}
  void updateShape() {
    std::vector<double> pos,m;for(auto &a:carts){pos.push_back(q+a.phase+a.offset);m.push_back(c.tare()+a.payload);}
    route.equilibrium(pos,m);last_shape=t;path_d.clear();path_dd.clear();
    double ds=c.derivative_step;
    for(size_t j=0;j<pos.size();++j) {
      V3 before=route.movedLoadPoint(j,pos[j]-ds,pos,m),after=route.movedLoadPoint(j,pos[j]+ds,pos,m);
      V3 here=route.at(pos[j]).p;path_d.push_back((after-before)/(2*ds));
      path_dd.push_back((after+before-here*2)/(ds*ds));
    }
    require(route.tensionMax()<c.max_tension,"computed tension exceeds conceptual domain; not clipped");
  }
  void refreshPositions() {
    for(size_t j=0;j<carts.size();++j) {auto &a=carts[j];a.pivot=route.at(q+a.phase+a.offset).p;
      a.pallet=a.pivot+V3{c.suspension*std::sin(a.tx),c.suspension*std::sin(a.ty),
        -c.suspension*std::cos(a.tx)*std::cos(a.ty)};
      a.velocity=path_d[j]*(v+a.offset_speed)+
        V3{c.suspension*std::cos(a.tx)*a.wx,c.suspension*std::cos(a.ty)*a.wy,0};}
  }
  bool stoppedAt(double s) const {
    const auto &a=carts.front();double d=wrap(q+a.phase+a.offset-s+route.total/2,route.total)-route.total/2;
    return std::abs(d)<c.station_tolerance&&std::abs(v)<c.stop_speed&&std::abs(a.offset_speed)<c.stop_speed;
  }
  double payloadSpecificEnergy(size_t id) const {
    const auto &a=carts[id];const auto &d=path_d[id];
    // Derivative of energy() with respect to payload at fixed shape and state.
    // Keep the same separated translational/pendulum kinetic approximation.
    return .5*d.dot(d)*sq(v+a.offset_speed)+.5*sq(c.suspension)*(sq(a.wx)+sq(a.wy))+
      g*a.pivot.z-g*c.suspension*std::cos(a.tx)*std::cos(a.ty);
  }
  void operation(double h) {
    bool loading=stage==0,unloading=stage==2;if(!loading&&!unloading)return;
    int &status=loading?load_status:unload_status;
    double start=loading?1:topArrival()+1,target=loading?0:route.lane_length;
    if(t<start||status==2)return;
    if(status==0&&stoppedAt(target)) {status=1;operation_start=t;
      events.push_back({t,loading?"load_begin":"unload_begin",0,carts[0].payload,loading?c.nominal_payload:0});}
    if(status==1) {
      require(stoppedAt(target),"load/unload outside stopped station");
      for(size_t i=0;i<(c.single_span?carts.size():1);++i) {
      auto &a=carts[i];double before=a.payload,u=smooth((t+h-operation_start)/c.payload_ramp);
      if(c.single_span) {
        double expected=i?(loading?route.lane_length+pi*c.lane_half_width:2*route.lane_length+pi*c.lane_half_width):target;
        double error=wrap(q+a.phase+a.offset-expected+route.total/2,route.total)-route.total/2;
        require(std::abs(a.offset_speed)<c.stop_speed&&std::abs(error)<c.station_tolerance,"carrier not present/stopped during service");
      }
      double payload=i?c.descending_payload:c.nominal_payload;
      a.payload=payload*(loading?u:1-u);
      // Mass/energy enter or leave through the loading operation, not through the motor.
      load_energy+=(a.payload-before)*payloadSpecificEnergy(i);
      if(t+h-operation_start>=c.payload_ramp) {status=2;events.push_back({t+h,loading?"load_end":"unload_end",int(i),
        loading?0:payload,a.payload});}
      }
    }
  }
  double energy() const {
    double e=.5*c.main_equivalent_mass*v*v+route.cableEnergy();
    for(size_t j=0;j<carts.size();++j) {auto &a=carts[j];double m=c.tare()+a.payload,mh=c.hanger_mass+c.pallet_mass+a.payload;
      V3 d=path_d[j];e+=.5*m*d.dot(d)*sq(v+a.offset_speed)+.5*c.coupling_k*sq(a.offset)+
        .5*mh*sq(c.suspension)*(sq(a.wx)+sq(a.wy))+m*g*a.pivot.z-mh*g*c.suspension*std::cos(a.tx)*std::cos(a.ty);}
    return e;
  }
  double residual() const {return energy()-energy0-(drive_work+local_work+wind_work+load_energy-loss_work-stop_loss);}
  void step(double h) {
    require(h>0&&h<=.01,"bad integration step");if(complete)return;
    h=std::min(h,duration()-t);
    if(program)program->beforeStep(*this,h);else {stage=stageAt(t);operation(h);}
    if(t-last_shape>=c.shape_period-1e-10)updateShape();
    auto ref=reference(t);double coupling_sum=0;std::vector<V3> d,dd;
    for(size_t j=0;j<carts.size();++j) {auto &a=carts[j];
      d.push_back(path_d[j]);dd.push_back(path_dd[j]);
      double horizontal=std::hypot(d.back().x,d.back().y);
      double rate=(a.wx*d.back().x+a.wy*d.back().y)/std::max(.1,horizontal);
      double raw=hybrid?c.local_damping_gain*rate:0;
      a.local_force=std::clamp(raw,-c.local_force_limit,c.local_force_limit);
      if(std::abs(a.offset_speed)>=c.local_speed&&a.local_force*a.offset_speed>0)a.local_force=0;
      if(std::abs(a.offset)>=c.local_stroke*.95&&a.local_force*a.offset>0)a.local_force=0;
      a.saturation=std::abs(raw-a.local_force)>1e-8;
      a.connector=-c.coupling_k*a.offset-c.coupling_c*a.offset_speed+a.local_force;coupling_sum+=a.connector;
    }
    // Ideal inner force servo with finite authority; q is integrated, never assigned to the reference.
    double desired_a=ref.a+4*(ref.s-q)+4*(ref.v-v);
    double raw_main=c.main_equivalent_mass*desired_a+coupling_sum+c.main_drag*v;
    main_force=std::clamp(raw_main,-c.main_force_limit,c.main_force_limit);
    double qa=(main_force-coupling_sum-c.main_drag*v)/c.main_equivalent_mass;
    if(gust&&wind_on<0&&stage==3&&q>route.lane_length+pi*c.lane_half_width+.25*route.lane_length) {
      wind_on=t;wind_end=t+c.wind_duration;events.push_back({t,"gust_begin",-1,0,c.wind_speed});}
    if(wind_end>=0&&t>=wind_end&&!gust_end_recorded){events.push_back({t,"gust_end",-1,c.wind_speed,0});gust_end_recorded=true;}
    wind=0;if(wind_on>=0&&t>=wind_on&&t<=wind_end)wind=c.wind_speed*sq(std::sin(pi*(t-wind_on)/c.wind_duration));
    V3 flow{wind*std::cos(c.wind_bearing_deg*pi/180),wind*std::sin(c.wind_bearing_deg*pi/180),0};
    double lp=0,wp=0,dp=c.main_drag*v*v;
    std::vector<V3> old;for(auto &a:carts)old.push_back(a.pallet);
    for(size_t j=0;j<carts.size();++j) {auto &a=carts[j];double m=c.tare()+a.payload,mh=c.hanger_mass+c.pallet_mass+a.payload;
      double G=std::max(.1,d[j].dot(d[j])),ui=v+a.offset_speed;
      double rolling=c.rolling_coefficient*ui;
      double ea=(a.connector-m*g*d[j].z-rolling-m*d[j].dot(dd[j])*ui*ui)/(m*G)-qa;
      double old_offset_speed=a.offset_speed;
      double area=c.area_empty+c.area_per_kg*a.payload;
      V3 relative=flow-a.velocity;a.wind_force=relative*(.5*c.air_density*c.drag_coefficient*area*relative.norm());
      lp+=a.local_force*a.offset_speed;wp+=a.wind_force.dot(a.velocity);
      dp+=rolling*ui+c.coupling_c*sq(a.offset_speed)+mh*sq(c.suspension)*c.swing_damping*(sq(a.wx)+sq(a.wy));
      a.offset_speed+=ea*h;
      // Explicit ideal speed governor and mechanical end stops; dissipated energy is recorded.
      if(std::abs(a.offset_speed)>c.local_speed) {double before=.5*m*G*sq(v+a.offset_speed);
        a.offset_speed=std::copysign(c.local_speed,a.offset_speed);stop_loss+=std::max(0.,before-.5*m*G*sq(v+a.offset_speed));++a.stops;}
      a.offset+=a.offset_speed*h;
      if(std::abs(a.offset)>c.local_stroke) {a.offset=std::copysign(c.local_stroke,a.offset);stop_loss+=.5*m*G*sq(a.offset_speed);a.offset_speed=0;++a.stops;}
      double actual_ea=(a.offset_speed-old_offset_speed)/h;
      V3 support_a=d[j]*(qa+actual_ea)+dd[j]*(ui*ui);
      // Two pendulum modes in global horizontal axes. Vertical cable load split is quasistatic.
      double effective_g=g+support_a.z;
      require(effective_g>.2*g&&effective_g<3*g,"vertical acceleration outside pendulum domain");
      double ax=-effective_g/c.suspension*std::sin(a.tx)-c.swing_damping*a.wx-support_a.x/c.suspension+a.wind_force.x/(mh*c.suspension);
      double ay=-effective_g/c.suspension*std::sin(a.ty)-c.swing_damping*a.wy-support_a.y/c.suspension+a.wind_force.y/(mh*c.suspension);
      a.wx+=ax*h;a.wy+=ay*h;a.tx+=a.wx*h;a.ty+=a.wy*h;
      require(std::isfinite(a.tx)&&std::abs(a.tx)<c.max_swing&&std::abs(a.ty)<c.max_swing,"pendulum outside small-angle domain");
      peak_local=std::max(peak_local,std::abs(a.local_force));peak_swing=std::max(peak_swing,std::hypot(a.tx,a.ty));
      local_peak_offset=std::max(local_peak_offset,std::abs(a.offset));local_peak_speed=std::max(local_peak_speed,std::abs(a.offset_speed));
    }
    double mp=main_force*v;drive_work+=mp*h;local_work+=lp*h;wind_work+=wp*h;loss_work+=dp*h;
    drive_positive+=std::max(0.,mp)*h;drive_absorbed+=std::max(0.,-mp)*h;
    local_positive+=std::max(0.,lp)*h;local_absorbed+=std::max(0.,-lp)*h;
    v+=qa*h;q+=v*h;t+=h;refreshPositions();
    peak_force=std::max(peak_force,std::abs(main_force));peak_tension=std::max(peak_tension,route.tensionMax());
    max_reference_error=std::max(max_reference_error,std::abs(q-reference(t).s));
    for(size_t j=0;j<carts.size();++j) {auto &a=carts[j];
      max_step_displacement=std::max(max_step_displacement,(a.pallet-old[j]).norm());
      double clearance=a.pallet.z-.2-route.ground(a.pallet.x);min_ground=std::min(min_ground,clearance);
      require(clearance>c.min_clearance,"pallet clearance outside conceptual domain");
      for(size_t k=j+1;k<carts.size();++k) {double gap=(a.pallet-carts[k].pallet).norm();min_gap=std::min(min_gap,gap);
        require(gap>1.5,"pallet envelopes overlap");}}
    require(std::isfinite(q)&&std::isfinite(v)&&std::isfinite(energy()),"nonfinite state");
    if(program)program->afterStep(*this);
    else if(t>=duration()-1e-8) {require(load_status==2&&unload_status==2,"script did not service loading stations");
      require(std::abs(q-route.total)<c.station_tolerance,"full loop incomplete");complete=true;
      events.push_back({t,"complete",-1,0,0});}
  }
};
// Static force envelope, not native support dynamics or structural approval.
// Two symmetric cables per lane; vertical reactions include cable self-weight.
struct BallastResult {
  double water_kg,mass_kg,cg_z,normal_N,horizontal_N,moment_Nm,sliding_margin,overturn_margin,pressure_Pa;
  bool in_domain;
};
inline BallastResult ballast(const Simulation &s,int station) {
  const auto &c=s.c;require(c.single_span&&(station==0||station==1),"ballast requires two-station topology");
  double water=1000*(c.ballast_litres/1000)*c.ballast_fill,mass=c.station_dry_mass+water;
  double cg=(c.station_dry_mass*c.dry_cg_z+water*(c.tank_bottom+c.tank_height*c.ballast_fill/2))/mass;
  double horizontal=0,vertical=0,moment=0;
  for(auto &lane:s.route.spans) {
    const auto &span=lane.front();horizontal+=2*span.H;
    vertical+=2*(station?span.rightReaction():span.leftReaction());
  }
  double X=c.terrain.back().first,Z=c.terrain.back().second-c.terrain.front().second;
  double slope=Z/X;
  // Conservative branch tension bound: T0 and T0+abs(motor force).
  // No claim of a resolved tractor sag/tension field.
  double tractorH=(2*c.tractor_pretension+std::abs(s.main_force))/std::hypot(1.,slope);
  vertical+=(station?1:-1)*tractorH*slope;
  moment=horizontal*c.support_height+tractorH*(c.support_height+c.tractor_lift)+c.base_offset*std::abs(vertical);
  horizontal+=tractorH;
  for(const auto &a:s.carts) {
    auto p=s.route.at(s.q+a.phase+a.offset);
    double guideFraction=1-p.cable_weight;
    int end=p.p.x<X/2?0:1;
    if(end==station) {
      double weight=(c.tare()+a.payload)*g*guideFraction;
      vertical+=weight;
      moment+=weight*std::abs(p.p.x-(station?X+c.base_offset:-c.base_offset)); // conservative overturn envelope
    }
    // Bound the entire horizontal aerodynamic force at each station separately;
    // no claim that this is an identified dynamic load-sharing law.
    double windBound=std::hypot(a.wind_force.x,a.wind_force.y);
    horizontal+=windBound;moment+=windBound*c.support_height;
  }
  double normal=mass*g+vertical;
  double slide=c.soil_mu*normal/std::max(1e-9,horizontal);
  double overturn=normal*std::min(c.base_x,c.base_y)/2/std::max(1e-9,moment);
  return {water,mass,cg,normal,horizontal,moment,slide,overturn,normal/(c.base_x*c.base_y),normal>0&&slide>=1&&overturn>=1};
}
} // namespace agro::loop
