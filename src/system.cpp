#include "agro/physics.hpp"
#include <gz/sim/System.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/Link.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Link.hh>
#include <gz/plugin/Register.hh>
#include <gz/transport/Node.hh>
#include <gz/msgs/double.pb.h>
#include <gz/msgs/double_v.pb.h>
#include <gz/msgs/pose.pb.h>
#include <fstream>
#include <iomanip>
#include <mutex>

namespace agro {
static Vec eigen(const gz::math::Vector3d &v) {return {v.X(),v.Y(),v.Z()};}
static gz::math::Vector3d gzvec(const Vec &v) {return {v.x(),v.y(),v.z()};}
class CableSystem: public gz::sim::System, public gz::sim::ISystemConfigure,
  public gz::sim::ISystemPreUpdate {
  gz::transport::Node node;
  gz::transport::Node::Publisher telemetry;
  gz::sim::Entity body=gz::sim::kNullEntity,model=gz::sim::kNullEntity;
  std::vector<gz::sim::Entity> cableModels;
  std::mutex mutex;
  std::string scenario,output;
  double span=20,slope=0,height=5,mass=15,speed=.5,dt=0,duration=120;
  double k=5000,damping=40,tmin=3,tmax=500,winchSpeed=.5,mu=.65,pendulum=.6,separation=1.2;
  double x=1,v=0,theta=0,omega=0,roll=0,rollRate=0,goalX=1;
  double referenceSpeed=0,clampForce=150;
  double logTime=-1,shapeTime=-1,visualTime=-1;
  double effort=0,residual=0,saturation=0,rejected=0,external=0;
  bool demo=true,perturbation=false,initialized=false,valid=true,renderCables=true;
  std::unique_ptr<Catenary> cable;
  std::unique_ptr<SpiderGeometry> spider;
  V8 rest=V8::Zero(),tensions=V8::Zero(),lengths=V8::Zero(),rates=V8::Zero();
  Vec position=Vec::Zero(),velocity=Vec::Zero(),rpy=Vec::Zero(),angvel=Vec::Zero();
  Vec target=Vec::Zero(),targetRPY=Vec::Zero(),requested=Vec::Zero(),requestedRPY=Vec::Zero();
  bool pending=false;
  std::ofstream csv;
  template<typename T> T get(const std::shared_ptr<const sdf::Element> &s,const std::string &name,T fallback) {
    return s->HasElement(name)?s->Get<T>(name):fallback;
  }
  bool feasible(const Vec &p,const Vec &angles) {
    // Explicit conservative operational box, checked in addition to wrench feasibility.
    if(p.x()<7||p.x()>13||std::abs(p.y())>3||p.z()-p.x()*slope<3||p.z()-p.x()*slope>7||angles.cwiseAbs().maxCoeff()>.26) return false;
    V6 w=V6::Zero();w[2]=mass*gravity;
    return allocate(spider->matrix(p,rotation(angles.x(),angles.y(),angles.z())),w,tmin,tmax).feasible;
  }
  void cartTarget(const gz::msgs::Double &msg) {
    std::lock_guard<std::mutex> lock(mutex);
    if(!std::isfinite(msg.data())||msg.data()<1||msg.data()>span-1) {++rejected;return;}
    goalX=msg.data();external=1;
  }
  void poseTarget(const gz::msgs::Pose &msg) {
    std::lock_guard<std::mutex> lock(mutex);
    const auto &p=msg.position();const auto &q=msg.orientation();
    Eigen::Quaterniond quat(q.w(),q.x(),q.y(),q.z());
    requested=Vec(p.x(),p.y(),p.z());
    if(!requested.allFinite()||!quat.coeffs().allFinite()||quat.norm()<1e-9) {++rejected;return;}
    quat.normalize();
    requestedRPY=eigen(gz::math::Quaterniond(quat.w(),quat.x(),quat.y(),quat.z()).Euler());pending=true;
  }
public:
  void Configure(const gz::sim::Entity &,const std::shared_ptr<const sdf::Element> &s,
                 gz::sim::EntityComponentManager &,gz::sim::EventManager &) override {
    scenario=get<std::string>(s,"scenario","single");output=get<std::string>(s,"output","telemetry.csv");
    span=get<double>(s,"span",20);slope=std::tan(get<double>(s,"slope_deg",15)*M_PI/180);
    height=get<double>(s,"support_height",5);mass=get<double>(s,"vehicle_mass",10)+get<double>(s,"payload",5);
    speed=get<double>(s,"max_speed",.5);duration=get<double>(s,"duration",120);
    mu=get<double>(s,"friction",.65);pendulum=get<double>(s,"pendulum_length",.6);
    separation=get<double>(s,"track_separation",1.2);
    clampForce=get<double>(s,"clamp_normal_force",150);
    k=get<double>(s,"spider_stiffness",5000);damping=get<double>(s,"spider_damping",40);
    tmin=get<double>(s,"spider_min_tension",3);tmax=get<double>(s,"spider_max_tension",500);
    winchSpeed=get<double>(s,"winch_speed",.5);demo=get<bool>(s,"demo",true);perturbation=get<bool>(s,"perturbation",false);
    renderCables=get<bool>(s,"render_cables",true);
    cable=std::make_unique<Catenary>(span,span*slope,std::hypot(span,span*slope)*(1+get<double>(s,"pretension_slack",.018)),get<double>(s,"cable_mass_per_m",.15)*gravity,get<double>(s,"cable_EA",2e6));
    spider=std::make_unique<SpiderGeometry>(slope);
    target=Vec(span/2,0,span/2*slope+5);requested=target;
    node.Subscribe("/agro/goal_x",&CableSystem::cartTarget,this);
    node.Subscribe("/agro/goal_pose",&CableSystem::poseTarget,this);
    telemetry=node.Advertise<gz::msgs::Double_V>("/agro/telemetry");
    csv.open(output);if(!csv) throw std::runtime_error("Cannot open telemetry: "+output);
    csv<<"time,x,y,z,roll,pitch,yaw,vx,vy,vz,wx,wy,wz,target_x,target_y,target_z,target_roll,target_pitch,target_yaw,position_error,orientation_error,effort,allocation_residual,feasible,rejected,saturated";
    for(int i=0;i<8;++i) csv<<",tension_"<<i<<",length_"<<i<<",winch_speed_"<<i;
    csv<<"\n";csv<<std::setprecision(10);
  }
  void PreUpdate(const gz::sim::UpdateInfo &info,gz::sim::EntityComponentManager &ecm) override {
    if(info.paused) return;
    dt=std::chrono::duration<double>(info.dt).count();
    const double time=std::chrono::duration<double>(info.simTime).count();
    if(dt<=0) return;
    std::lock_guard<std::mutex> lock(mutex);
    if(model==gz::sim::kNullEntity) {
      model=ecm.EntityByComponents(gz::sim::components::Model(),gz::sim::components::Name("vehicle"));
      if(model==gz::sim::kNullEntity) return;
      body=gz::sim::Model(model).LinkByName(ecm,"body");
      gz::sim::Link(body).EnableVelocityChecks(ecm,true);
      int count=renderCables?(scenario=="spider"?8:(scenario=="double"?2:1))*32:0;
      for(int i=0;i<count;++i) cableModels.push_back(ecm.EntityByComponents(gz::sim::components::Model(),gz::sim::components::Name("cable_"+std::to_string(i))));
    }
    if(scenario=="spider") updateSpider(time,ecm);else updateCart(time,ecm);
    if(time-visualTime>=.05) {drawCables(ecm);visualTime=time;}
    if(time-logTime>=.02-1e-8) {record(time);logTime=time;}
  }
private:
  void updateCart(double time,gz::sim::EntityComponentManager &ecm) {
    double referenceV=0;
    if(demo&&!external) {
      // Reference advances at a bounded speed along the cable, not along horizontal x.
      // Reserve 10% speed authority for feedback and brake smoothly near the endpoint.
      double endpoint=time<60?19:1;
      double direction=endpoint>goalX?1:-1;
      double metric=initialized?std::hypot(1.,cable->slope()):1.4;
      double desired=direction*std::min(.9*speed/metric,std::sqrt(.12*std::abs(endpoint-goalX)));
      if(time>=55&&time<60) desired=0;
      referenceSpeed+=std::clamp(desired-referenceSpeed,-.06*dt,.06*dt);
      double next=goalX+referenceSpeed*dt;
      if((endpoint-goalX)*(endpoint-next)<=0) {goalX=endpoint;referenceSpeed=0;}else goalX=next;
      referenceV=referenceSpeed;
    }
    if(time-shapeTime>=.02||!initialized) {
      valid=cable->solve(x,mass*gravity/(scenario=="double"?2:1));
      if(!valid) throw std::runtime_error("Catenary failed to converge");
      shapeTime=time;initialized=true;
    }
    double grade=cable->slope(),metric=std::sqrt(1+grade*grade);
    double desired=std::clamp(referenceV+2*(goalX-x),-speed/metric,speed/metric);
    double raw=mass*(4*(desired-v)*metric+gravity*grade/metric)+.6*v;
    double limit=mu*(mass*gravity/metric+clampForce);
    effort=std::clamp(raw,-limit,limit);saturation=std::abs(raw)>limit;
    double acceleration=(effort-mass*gravity*grade/metric-.6*v)/(mass*metric);
    v+=acceleration*dt;x+=v*dt;
    if(x<.5||x>span-.5) {x=std::clamp(x,.5,span-.5);v=0;}
    omega+=(-gravity/pendulum*std::sin(theta)-1.2*omega-acceleration/pendulum)*dt;theta+=omega*dt;
    const double disturbance=perturbation&&time>=35&&time<36?20:0;
    const double lateralStiffness=scenario=="double"?35:0;
    rollRate+=(-(gravity/pendulum+lateralStiffness)*std::sin(roll)-1.2*rollRate+disturbance/(mass*pendulum))*dt;roll+=rollRate*dt;
    position=Vec(x,pendulum*std::sin(roll),height+cable->height());
    velocity=Vec(v,pendulum*std::cos(roll)*rollRate,v*grade);
    rpy=Vec(roll,theta,0);angvel=Vec(rollRate,omega,0);
    // Reduced constrained dynamics: position is rendered, not used to claim wheel contact physics.
    gz::sim::Model(model).SetWorldPoseCmd(ecm,gz::math::Pose3d(gzvec(position),gz::math::Quaterniond(roll,theta,0)));
    target=Vec(goalX,0,position.z());targetRPY=Vec::Zero();
    tensions.setZero();lengths.setZero();tensions[0]=cable->maxTension();lengths[0]=cable->L;
    if(scenario=="double") {tensions[1]=tensions[0];lengths[1]=lengths[0];}
  }
  void updateSpider(double time,gz::sim::EntityComponentManager &ecm) {
    auto link=gz::sim::Link(body);
    auto pose=link.WorldPose(ecm);if(!pose) return;
    position=eigen(pose->Pos());rpy=eigen(pose->Rot().Euler());
    velocity=eigen(link.WorldLinearVelocity(ecm).value_or(gz::math::Vector3d::Zero));
    angvel=eigen(link.WorldAngularVelocity(ecm).value_or(gz::math::Vector3d::Zero));
    Eigen::Quaterniond quat(pose->Rot().W(),pose->Rot().X(),pose->Rot().Y(),pose->Rot().Z());
    Eigen::Matrix3d R=quat.toRotationMatrix();
    if(pending) {
      bool allowed=true;
      for(int j=0;j<=20;++j) {double u=j/20.;if(!feasible((1-u)*position+u*requested,(1-u)*rpy+u*requestedRPY)) {allowed=false;break;}}
      if(allowed) {target=requested;targetRPY=requestedRPY;external=1;}else ++rejected;
      pending=false;
    }
    Vec targetVelocity=Vec::Zero();
    if(demo&&!external) {
      const double phase=2*M_PI*time/100;
      target=Vec(span/2+1.2*std::sin(phase),.8*std::sin(2*phase),span/2*slope+5+.4*std::sin(phase));
      targetVelocity=Vec(1.2*std::cos(phase),1.6*std::cos(2*phase),.4*std::cos(phase))*2*M_PI/100;
      targetRPY=Vec(.06*std::sin(phase),.06*std::sin(2*phase),.10*std::sin(phase));
    }
    Eigen::Matrix3d desiredR=rotation(targetRPY.x(),targetRPY.y(),targetRPY.z());
    Eigen::AngleAxisd rotationError(desiredR*R.transpose());
    Vec angularError=rotationError.axis()*rotationError.angle();
    Vec desiredVelocity=targetVelocity+2*(target-position);
    if(desiredVelocity.norm()>speed) desiredVelocity*=speed/desiredVelocity.norm();
    V6 wrench;
    wrench.head<3>()=mass*(6*(desiredVelocity-velocity)+Vec(0,0,gravity));
    wrench.tail<3>()=30*angularError-9*angvel;
    auto A=spider->matrix(position,R);
    auto allocation=allocate(A,wrench,tmin,tmax);
    residual=allocation.residual;valid=allocation.feasible;saturation=0;
    Vec total=Vec::Zero(),torque=Vec::Zero();
    for(int i=0;i<8;++i) {
      Vec r=R*spider->attachments[i];Vec delta=spider->anchors[i]-position-r;
      lengths[i]=delta.norm();Vec direction=delta/lengths[i];
      const double lengthRate=-direction.dot(velocity+angvel.cross(r));
      if(!initialized) rest[i]=lengths[i]-allocation.tensions[i]/k;
      double desiredRest=lengths[i]-(allocation.tensions[i]-damping*lengthRate)/k;
      rates[i]=std::clamp((desiredRest-rest[i])/dt,-winchSpeed,winchSpeed);
      saturation=std::max(saturation,std::abs(rates[i])>=winchSpeed?1.:0.);
      rest[i]+=rates[i]*dt;
      tensions[i]=cableTension(lengths[i],rest[i],lengthRate,k,damping);
      Vec force=direction*tensions[i];total+=force;torque+=r.cross(force);
    }
    initialized=true;
    if(perturbation&&time>=35&&time<36) total.y()+=20;
    link.AddWorldWrench(ecm,gzvec(total),gzvec(torque));
    effort=tensions.maxCoeff();
  }
  void drawCables(gz::sim::EntityComponentManager &ecm) {
    if(!renderCables) return;
    const int n=scenario=="spider"?8:(scenario=="double"?2:1);
    for(int c=0;c<n;++c) for(int j=0;j<32;++j) {
      Vec a,b;
      if(scenario=="spider") {
        Vec attach=position+rotation(rpy.x(),rpy.y(),rpy.z())*spider->attachments[c];
        a=spider->anchors[c]+(attach-spider->anchors[c])*(j/32.);
        b=spider->anchors[c]+(attach-spider->anchors[c])*((j+1)/32.);
      } else {
        auto ca=cable->point(cable->L*j/32.);auto cb=cable->point(cable->L*(j+1)/32.);
        double y=scenario=="double"?(c==0?-separation/2:separation/2):0;
        a=Vec(ca.x(),y,height+ca.y());b=Vec(cb.x(),y,height+cb.y());
      }
      Vec d=b-a;Eigen::Quaterniond q=Eigen::Quaterniond::FromTwoVectors(Vec::UnitZ(),d);
      auto entity=cableModels[c*32+j];if(entity!=gz::sim::kNullEntity)
        gz::sim::Model(entity).SetWorldPoseCmd(ecm,gz::math::Pose3d(gzvec((a+b)/2),gz::math::Quaterniond(q.w(),q.x(),q.y(),q.z())));
    }
  }
  void record(double time) {
    double pe=scenario=="spider"?(position-target).norm():std::abs(x-goalX);
    double oe=Eigen::AngleAxisd(rotation(targetRPY.x(),targetRPY.y(),targetRPY.z())*rotation(rpy.x(),rpy.y(),rpy.z()).transpose()).angle();
    std::vector<double> row={time,position.x(),position.y(),position.z(),rpy.x(),rpy.y(),rpy.z(),velocity.x(),velocity.y(),velocity.z(),angvel.x(),angvel.y(),angvel.z(),target.x(),target.y(),target.z(),targetRPY.x(),targetRPY.y(),targetRPY.z(),pe,oe,effort,residual,valid?1.:0.,rejected,saturation};
    for(int i=0;i<8;++i) {row.push_back(tensions[i]);row.push_back(lengths[i]);row.push_back(rates[i]);}
    gz::msgs::Double_V message;
    for(size_t i=0;i<row.size();++i) {if(i) csv<<",";csv<<row[i];message.add_data(row[i]);}
    csv<<"\n";telemetry.Publish(message);
    if(!position.allFinite()||!velocity.allFinite()||!tensions.allFinite()) throw std::runtime_error("Non-finite simulation state");
    if(time>=duration-.05) csv.flush();
  }
};
}
GZ_ADD_PLUGIN(agro::CableSystem,gz::sim::System,agro::CableSystem::ISystemConfigure,agro::CableSystem::ISystemPreUpdate)
