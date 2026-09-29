#pragma once
#include <Eigen/Dense>
#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace agro {
constexpr double gravity = 9.81;
using Vec = Eigen::Vector3d;
using Mat68 = Eigen::Matrix<double,6,8>;
using V8 = Eigen::Matrix<double,8,1>;
using V6 = Eigen::Matrix<double,6,1>;

// Exact elastic catenary in unstretched material coordinates. Weight w [N/m].
// A downward point load causes a positive jump in vertical tension.
struct Catenary {
  double D, dz, L, w, EA, H=100, V=-100, s=1, load=0;
  Catenary(double span, double rise, double length, double weight, double stiffness)
    : D(span), dz(rise), L(length), w(weight), EA(stiffness) {}
  Eigen::Vector2d segment(double h,double v,double length) const {
    const double end=v+w*length;
    return {h/w*(std::asinh(end/h)-std::asinh(v/h))+h*length/EA,
      (std::hypot(h,end)-std::hypot(h,v))/w+(v*length+0.5*w*length*length)/EA};
  }
  Vec residual(const Vec &u,double x,double p) const {
    double h=std::exp(u[0]);
    auto a=segment(h,u[1],u[2]);
    auto b=segment(h,u[1]+w*u[2]+p,L-u[2]);
    return {a[0]-x,a[0]+b[0]-D,a[1]+b[1]-dz};
  }
  bool solve(double x,double p) {
    x=std::clamp(x,0.05,D-0.05);
    Vec u(std::log(std::max(20.0,H)),V,std::clamp(s,0.001,L-0.001));
    if (load==0) {u[1]=-p*0.5-w*L*0.5+std::exp(u[0])*dz/D;u[2]=L*x/D;}
    for(int it=0;it<70;++it) {
      Vec r=residual(u,x,p);
      if(r.norm()<1e-8) {H=std::exp(u[0]);V=u[1];s=u[2];load=p;return true;}
      Eigen::Matrix3d J;
      for(int j=0;j<3;++j) {Vec v=u;double e=1e-5*std::max(1.0,std::abs(u[j]));v[j]+=e;J.col(j)=(residual(v,x,p)-r)/e;}
      Vec step=J.fullPivLu().solve(r);
      bool accepted=false;
      for(double a=1;a>1e-7;a*=0.5) {
        Vec v=u-a*step;
        if(v[0]<-5||v[0]>18||v[2]<=0||v[2]>=L) continue;
        if(residual(v,x,p).norm()<r.norm()) {u=v;accepted=true;break;}
      }
      if(!accepted) return false;
    }
    return false;
  }
  Eigen::Vector2d point(double material) const {
    if(material<=s) return segment(H,V,material);
    return segment(H,V,s)+segment(H,V+w*s+load,material-s);
  }
  double height() const {return point(s)[1];}
  double slope() const {return (V+w*s+0.5*load)/H;}
  double maxTension() const {return std::max({std::hypot(H,V),std::hypot(H,V+w*s),std::hypot(H,V+w*s+load),std::hypot(H,V+w*L+load)});}
};

struct Allocation { V8 tensions; double residual; bool feasible; };
inline Allocation allocate(const Mat68 &A,const V6 &wrench,double lo,double hi) {
  // Box-constrained least squares: projected gradient, with a feasible warm start.
  V8 t=V8::Constant((lo+hi)*0.1);
  t += A.transpose()*(A*A.transpose()).ldlt().solve(wrench-A*t);
  if(t.allFinite() && (t.array()>=lo).all() && (t.array()<=hi).all()) {
    const double r=(A*t-wrench).norm();return {t,r,r<0.1};
  }
  t=t.cwiseMax(lo).cwiseMin(hi);
  const double alpha=1.0/std::max(1e-9,A.squaredNorm());
  for(int i=0;i<1500;++i) {
    V8 next=(t+alpha*A.transpose()*(wrench-A*t)).cwiseMax(lo).cwiseMin(hi);
    if((next-t).norm()<1e-9) {t=next;break;}
    t=next;
  }
  const double r=(A*t-wrench).norm();
  return {t,r,r<0.1};
}
inline double cableTension(double length,double rest,double radialSpeed,double k,double c) {
  if(length<=rest) return 0.0;
  return std::max(0.0,k*(length-rest)+c*radialSpeed);
}
inline Eigen::Matrix3d rotation(double roll,double pitch,double yaw) {
  return (Eigen::AngleAxisd(yaw,Vec::UnitZ())*Eigen::AngleAxisd(pitch,Vec::UnitY())*Eigen::AngleAxisd(roll,Vec::UnitX())).toRotationMatrix();
}
struct SpiderGeometry {
  std::array<Vec,8> anchors, attachments;
  SpiderGeometry(double slope) {
    // Crossed upper and lower cables give a full-rank wrench matrix near the centre.
    for(int i=0;i<8;++i) {
      const int j=i%4; double angle=M_PI/4+j*M_PI/2;
      double ax=10+7*std::cos(angle), ay=7*std::sin(angle);
      anchors[i]=Vec(ax,ay,10*slope+(i<4?10.0:2.0));
      double b=angle+(j%2==0?0.65:-0.65);
      attachments[i]=Vec(0.6*std::cos(b),0.6*std::sin(b),i<4?0.25:-0.25);
    }
  }
  Mat68 matrix(const Vec &pos,const Eigen::Matrix3d &R) const {
    Mat68 A;
    for(int i=0;i<8;++i) {Vec r=R*attachments[i],d=(anchors[i]-pos-r).normalized();A.col(i).head<3>()=d;A.col(i).tail<3>()=r.cross(d);}
    return A;
  }
};
}
