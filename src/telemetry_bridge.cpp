#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <gz/transport/Node.hh>
#include <gz/msgs/double_v.pb.h>

// Jazzy's standard bridge has no Double_V / Float64MultiArray conversion.
// Preserve precision of simulation time and cable states.
int main(int argc,char **argv) {
  rclcpp::init(argc,argv);
  auto node=std::make_shared<rclcpp::Node>("agro_telemetry_bridge");
  auto publisher=node->create_publisher<std_msgs::msg::Float64MultiArray>("/agro/telemetry",10);
  {
    gz::transport::Node transport;
    std::function<void(const gz::msgs::Double_V &)> callback=[publisher](const gz::msgs::Double_V &message) {
      std_msgs::msg::Float64MultiArray result;
      result.data.assign(message.data().begin(),message.data().end());
      publisher->publish(result);
    };
    if(!transport.Subscribe("/agro/telemetry",callback)) return 1;
    rclcpp::spin(node);
  }
  rclcpp::shutdown();
  return 0;
}
