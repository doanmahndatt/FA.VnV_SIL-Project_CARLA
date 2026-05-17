import carla


class SimpleController():

    def __init__(self, actor, args):

        print("SimpleController init")

        self.actor = actor

        self.world = actor.get_world()

        self.spectator = self.world.get_spectator()

        self.target_speed = 0

        self.waypoints = []


    def reset(self):

        pass


    def update_target_speed(self, speed):

        self.target_speed = speed


    def update_waypoints(self, waypoints):

        self.waypoints = waypoints


    def check_reached_waypoint_goal(self):

        # luôn trả False để route luôn active
        return False


    def run_step(self):

        transform = self.actor.get_transform()


        # camera follow EV
        cam_loc = transform.location + carla.Location(x=-8, z=3)

        cam_rot = carla.Rotation(
            pitch=-12,
            yaw=transform.rotation.yaw
        )

        self.spectator.set_transform(
            carla.Transform(cam_loc, cam_rot)
        )


        control = carla.VehicleControl()

        control.throttle = 0.35
        control.steer = 0
        control.brake = 0


        return control