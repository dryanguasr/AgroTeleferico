#include "agro/physics.hpp"
#include <iostream>
void require(bool condition,const char *message) {if(!condition) throw std::runtime_error(message);}
int main() {
  using namespace agro;
  Catenary c(20,0,20.5,1.5,2e6);
  require(c.solve(10,100),"loaded catenary converges");
  require(std::abs(c.point(c.L)[0]-20)<1e-6,"horizontal boundary");
  require(std::abs(c.point(c.L)[1])<1e-6,"vertical boundary");
  require(std::abs(c.V+0.5*(c.w*c.L+100))<1e-4,"support reactions balance weight");
  require(c.height()<0,"downward sag");
  // Independent inextensible symmetric catenary: L=2a sinh(D/(2a)).
  Catenary unloaded(20,0,20.5,1.5,1e14);
  require(unloaded.solve(10,0),"unloaded catenary converges");
  double low=1,high=1000;
  for(int i=0;i<100;++i) {double a=(low+high)/2;if(2*a*std::sinh(10/a)>20.5) low=a;else high=a;}
  double a=(low+high)/2;
  require(std::abs(unloaded.height()+a*(std::cosh(10/a)-1))<1e-6,"analytic sag");
  for(double p:{98.1,147.15,196.2}) for(double x:{1.,5.,10.,15.,19.}) {
    Catenary inclined(20,20*std::tan(M_PI/12),21.08,1.4715,2e6);
    require(inclined.solve(x,p),"inclined moving load equilibrium");
    require(inclined.maxTension()>0,"positive tension");
  }
  require(cableTension(1,2,100,5000,40)==0,"slack never pushes");
  require(cableTension(2,1,-1000,5000,40)==0,"damping never creates compression");
  SpiderGeometry g(std::tan(M_PI/12));Vec p(10,0,10*std::tan(M_PI/12)+5);
  auto A=g.matrix(p,Eigen::Matrix3d::Identity());
  require(A.fullPivLu().rank()==6,"six controllable degrees of freedom");
  V6 w=V6::Zero();w[2]=147.15;auto result=allocate(A,w,3,500);
  std::cout<<"Allocation residual "<<result.residual<<" tensions "<<result.tensions.transpose()<<std::endl;
  require(result.feasible,"static pose feasible");
  require((result.tensions.array()>=3).all(),"minimum tension");
  for(double m:{10.,15.,20.}) for(int j=0;j<100;++j) {
    double phase=2*M_PI*j/100;
    Vec pos=p+Vec(1.2*std::sin(phase),.8*std::sin(2*phase),.4*std::sin(phase));
    auto R=rotation(.06*std::sin(phase),.06*std::sin(2*phase),.10*std::sin(phase));
    V6 staticWrench=V6::Zero();staticWrench[2]=m*gravity;
    require(allocate(g.matrix(pos,R),staticWrench,3,500).feasible,"entire demonstration statically feasible");
  }
  w[2]=1e6;require(!allocate(A,w,3,500).feasible,"unreachable wrench rejected");
  std::cout<<"Physics checks passed\n";
}
