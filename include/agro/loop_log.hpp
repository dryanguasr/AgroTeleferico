#pragma once
#include "agro/loop.hpp"
#include <filesystem>
#include <chrono>
namespace agro::loop {
class Log {
  std::filesystem::path dir;
  std::ofstream global,carriers,cables;
  std::string origin;
  double last=-1;
  std::chrono::steady_clock::time_point wall=std::chrono::steady_clock::now();
 public:
  Log(const std::string &output,const std::string &backend):dir(output),origin(backend) {
    std::filesystem::create_directories(dir);
    for(auto name:{"global.csv","carriers.csv","cables.csv","summary.json"})
      require(!std::filesystem::exists(dir/name),"output already exists; choose a new directory: "+(dir/name).string());
    global.open(dir/"global.csv");carriers.open(dir/"carriers.csv");cables.open(dir/"cables.csv");
    require(bool(global)&&bool(carriers)&&bool(cables),"cannot open logs");
    global<<"time_s,stage,q_m,reference_m,speed_m_s,force_N,torque_Nm,power_W,wind_m_s,max_tension_N,max_sag_m,drive_positive_J,drive_absorbed_J,local_positive_J,local_absorbed_J,wind_work_J,loss_work_J,load_energy_J,stop_loss_J,energy_J,residual_J\n";
    carriers<<"time_s,id,lane,span,reference_s_m,offset_m,offset_speed_m_s,payload_kg,total_mass_kg,pivot_x_m,pivot_y_m,pivot_z_m,pallet_x_m,pallet_y_m,pallet_z_m,vx_m_s,vy_m_s,vz_m_s,swing_x_rad,swing_y_rad,rate_x_rad_s,rate_y_rad_s,connector_N,local_force_N,local_power_W,saturated,governor_or_stop_count,force_wind_x_N,force_wind_y_N\n";
    cables<<"time_s,lane,span,x0_m,x1_m,rest_length_m,H_N,max_tension_N,sag_m,load_per_cable_N,left_reaction_N,right_reaction_N,elastic_per_cable_J\n";
    global<<std::setprecision(10);carriers<<std::setprecision(10);cables<<std::setprecision(10);
  }
  void record(const Simulation &s,bool force=false) {
    if(!force&&s.t-last<s.c.log_period-1e-8)return;
    last=s.t;
    global<<s.t<<','<<s.stage<<','<<s.q<<','<<s.reference(s.t).s<<','<<s.v<<','<<s.main_force<<','<<s.main_force*s.c.drive_radius<<','<<s.main_force*s.v<<','<<s.wind<<','<<s.route.tensionMax()<<','<<s.route.sagMax()<<','<<s.drive_positive<<','<<s.drive_absorbed<<','<<s.local_positive<<','<<s.local_absorbed<<','<<s.wind_work<<','<<s.loss_work<<','<<s.load_energy<<','<<s.stop_loss<<','<<s.energy()<<','<<s.residual()<<'\n';
    for(size_t i=0;i<s.carts.size();++i) {auto &a=s.carts[i];auto p=s.route.at(s.q+a.phase+a.offset);
      carriers<<s.t<<','<<i<<','<<p.lane<<','<<p.span<<','<<wrap(s.q+a.phase+a.offset,s.route.total)<<','<<a.offset<<','<<a.offset_speed<<','<<a.payload<<','<<s.c.tare()+a.payload<<','<<a.pivot.x<<','<<a.pivot.y<<','<<a.pivot.z<<','<<a.pallet.x<<','<<a.pallet.y<<','<<a.pallet.z<<','<<a.velocity.x<<','<<a.velocity.y<<','<<a.velocity.z<<','<<a.tx<<','<<a.ty<<','<<a.wx<<','<<a.wy<<','<<a.connector<<','<<a.local_force<<','<<a.local_force*a.offset_speed<<','<<a.saturation<<','<<a.stops<<','<<a.wind_force.x<<','<<a.wind_force.y<<'\n';}
    for(int lane=0;lane<2;++lane)for(size_t i=0;i<s.route.spans[lane].size();++i) {auto &a=s.route.spans[lane][i];double sum=0;for(auto p:a.loads)sum+=p.weight;
      cables<<s.t<<','<<lane<<','<<i<<','<<a.x0<<','<<a.x1<<','<<a.L0<<','<<a.H<<','<<a.maxT<<','<<a.sag<<','<<sum<<','<<a.leftReaction()<<','<<a.rightReaction()<<','<<a.elastic<<'\n';}
  }
  void finish(const Simulation &s,const std::string &status="completed") {
    record(s,true);global.flush();carriers.flush();cables.flush();
    double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-wall).count();
    double stops=0;for(auto &a:s.carts)stops+=a.stops;
    std::ofstream f(dir/"summary.json");f<<std::setprecision(12);
    f<<"{\n  \"schema\": \"agro-loop-v1\",\n  \"origin\": \""<<origin<<"\",\n  \"status\": \""<<status<<"\",\n  \"mode\": \""<<(s.hybrid?"central_local":"central_only")<<"\",\n  \"gust_enabled\": "<<(s.gust?"true":"false")<<",\n";
#define J(name,value) f<<"  \""<<name<<"\": "<<(value)<<",\n"
    J("simulated_s",s.t);J("duration_target_s",s.duration());J("wall_s",seconds);J("simulation_to_wall_ratio",s.t/std::max(seconds,1e-9));
    J("carriers",s.carts.size());J("unique_supports",s.route.support_x.size());J("reference_loop_m",s.route.total);J("final_q_m",s.q);
    J("max_reference_error_m",s.max_reference_error);J("peak_main_force_N",s.peak_force);J("peak_main_torque_Nm",s.peak_force*s.c.drive_radius);
    J("peak_local_force_N",s.peak_local);J("max_swing_rad",s.peak_swing);J("peak_tension_N",s.peak_tension);
    J("min_pallet_ground_clearance_m",s.min_ground);J("min_carrier_center_distance_m",s.min_gap);
    J("max_step_pallet_displacement_m",s.max_step_displacement);J("max_local_offset_m",s.local_peak_offset);J("max_local_speed_m_s",s.local_peak_speed);
    J("governor_or_stop_count",stops);J("drive_positive_J",s.drive_positive);J("drive_absorbed_J",s.drive_absorbed);
    J("local_positive_J",s.local_positive);J("local_absorbed_J",s.local_absorbed);J("load_energy_J",s.load_energy);J("energy_residual_J",s.residual());
    J("loaded_kg",s.load_status==2?s.c.nominal_payload:0);J("unloaded_kg",s.unload_status==2?s.c.nominal_payload:0);
    J("gust_start_s",s.wind_on);J("gust_end_s",s.wind_end);
#undef J
    f<<"  \"signal_provenance\": {\"poses_and_angles\": \"reduced_model_state\", \"cables\": \"quasistatic_elastic_equilibrium\", \"wind_and_dispatch\": \"scripted_inputs\", \"forces_and_energy\": \"reduced_model_estimates\"},\n";
    f<<"  \"limits\": [\"not native Gazebo contact dynamics\", \"not physical validation or Sim2Real\", \"absorbed mechanical energy is not stored electricity\", \"pendulum reaction and cable shape-rate coupling are incomplete; inspect energy residual\"],\n  \"events\": [";
    for(size_t i=0;i<s.events.size();++i) {auto &e=s.events[i];if(i)f<<',';f<<"{\"time_s\":"<<e.time<<",\"name\":\""<<e.name<<"\",\"carrier\":"<<e.carrier<<",\"from\":"<<e.from<<",\"to\":"<<e.to<<'}';}
    f<<"]\n}\n";
  }
};
}
