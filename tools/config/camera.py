import carla
import time

client = carla.Client("localhost", 2000)
client.set_timeout(10.0)

print("birdview camera started")

alpha = 0.12

prev_transform = None
world = None


def find_vehicle(world, role):

    for v in world.get_actors().filter("vehicle.*"):

        if v.attributes.get("role_name") == role:

            return v

    return None


while True:

    try:

        new_world = client.get_world()

        if world is None or world.id != new_world.id:

            world = new_world
            spectator = world.get_spectator()

            print("connected to world")


        ev = find_vehicle(world, "ev")

        if ev is None or not ev.is_alive:

            prev_transform = None
            time.sleep(0.05)
            continue


        ego_tf = ev.get_transform()


        # birdview ổn định
        target_location = ego_tf.location + carla.Location(z=32)

        target_rotation = carla.Rotation(

            pitch=-55,
            yaw=ego_tf.rotation.yaw

        )


        if prev_transform:

            loc = carla.Location(

                x = prev_transform.location.x
                + alpha*(target_location.x - prev_transform.location.x),

                y = prev_transform.location.y
                + alpha*(target_location.y - prev_transform.location.y),

                z = prev_transform.location.z
                + alpha*(target_location.z - prev_transform.location.z)

            )


            rot = carla.Rotation(

                pitch = -55,

                yaw = prev_transform.rotation.yaw
                + 0.18*(target_rotation.yaw - prev_transform.rotation.yaw),

                roll = 0

            )

        else:

            loc = target_location
            rot = target_rotation


        spectator.set_transform(carla.Transform(loc, rot))

        prev_transform = carla.Transform(loc, rot)


        time.sleep(0.05)


    except RuntimeError:

        world = None
        prev_transform = None
        time.sleep(1)