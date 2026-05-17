from srunner.autoagents.autonomous_agent import AutonomousAgent
import carla


class OpenpilotAgent(AutonomousAgent):

    def __init__(self, vehicle, config_file):

        super().__init__(vehicle)

        self.vehicle = vehicle
        self.world = vehicle.get_world()
        self.spectator = self.world.get_spectator()


    def setup(self, path_to_conf_file):

        print("Openpilot agent loaded")


    def sensors(self):

        return []


    def run_step(self):

        transform = self.vehicle.get_transform()

        loc = transform.location
        rot = transform.rotation


        # camera phía sau xe (giống game driving)
        camera_location = loc + carla.Location(
            x=-8,
            z=3
        )

        camera_rotation = carla.Rotation(
            pitch=-10,
            yaw=rot.yaw
        )


        self.spectator.set_transform(
            carla.Transform(
                camera_location,
                camera_rotation
            )
        )


        # dummy throttle để xe chạy
        control = carla.VehicleControl()

        control.throttle = 0.4
        control.steer = 0.0

        return control
        
    def run_step(self):

        print("agent tick")

        transform = self.vehicle.get_transform()

        cam_loc = transform.location + carla.Location(x=-8, z=3)

        cam_rot = carla.Rotation(
            pitch=-12,
            yaw=transform.rotation.yaw
        )

        self.spectator.set_transform(
            carla.Transform(cam_loc, cam_rot)
        )

        control = carla.VehicleControl()

        control.throttle = 0.3

        return control


    def reset(self):

        pass


    def destroy(self):

        pass