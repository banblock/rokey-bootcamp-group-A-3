main_task ="""
VELOCITY, ACC = 30, 30
OFF, ON = 0, 1
velx, accx = (70, 70)
velj, accj = (20, 20)

set_tool("Tool Weight1")
set_tcp("GripperDA_v2")

class BookReturnRobot:
    def __init__(self):

        self.velx = velx
        self.accx = accx
        self.velj = velj
        self.accj = accj

        self.z_max = 300

        self.first_pos = posj([0, 0, 90, 0, 90, 0])
        self.second_pos = posx([230, 487, 320, 65, 180, 65])
        self.third_pos = posx([339, 464, 310, 39, -180, 129])
        self.forth_pos = posx([94, 488, 250, 50, -180, 50])
        self.book_size = [130.0, 190.0, 16.0]


    def grip_close(self):
        set_digital_output(1, 0)
        set_digital_output(2, 1)
        wait(3)

    def grip_open(self):
        set_digital_output(1, 1)
        set_digital_output(2, 0)
        wait(3)

    def move_relative(self, dx=0, dy=0, dz=0, da=0, db=0, dc=0):
        movel(
            posx([dx, dy, dz, da, db, dc]),
            vel=self.velx,
            acc=self.accx,
            mod=DR_MV_MOD_REL,
        )

    def get_current_pose(self):
        return get_current_posx()[0]

    def force_down(self, force, diff=5):
        task_compliance_ctrl([3000.0, 3000.0, 3000.0, 200, 200, 200])
        wait(0.5)

        force_d = [0.0, 0.0, -force, 0.0, 0.0, 0.0]
        force_dir = [0, 0, 1, 0, 0, 0]

        set_desired_force(force_d, force_dir, mod=DR_FC_MOD_REL)
        wait(0.5)

        while True:
            f = get_tool_force(DR_BASE)

            if f[2] > force - diff:
                break

        release_force()
        wait(0.5)
        release_compliance_ctrl()
        wait(0.5)

    def start_task(self):
        self.grip_open()

    def move_to_initial_position(self):
        movej(self.first_pos, self.velj, self.accj)
        wait(0.5)

    def move_to_return_center_height(self):
        movel(self.second_pos, vel=self.velx, acc=self.accx)
        wait(0.5)

    def check_height_by_force(self):
        self.force_down(30, diff=25)
        wait(0.5)

    def move_to_right_max_position(self):
        self.move_relative(dz=10)

        current_pose = self.get_current_pose()
        wait(0.5)
        movel(
            posx([
                self.third_pos[0],
                self.third_pos[1],
                current_pose[2],
                self.third_pos[3],
                self.third_pos[4],
                self.third_pos[5],
            ]),
            vel=self.velx,
            acc=self.accx,
        )
        wait(0.5)

    def lower_by_half_book_thickness(self):
        self.move_relative(dz=-10 - self.book_size[2] / 2)
        wait(0.5)

    def push_book(self):
        self.move_relative(dx=-60)
        wait(0.5)

        self.move_relative(dx=10)
        wait(0.5)

    def move_above_book(self):
        self.move_relative(dz=10 + self.book_size[2] / 2)
        wait(0.5)


    def move_to_left_min_position(self):
        z = self.get_current_pose()[2]
        movel(
            posx([
                self.forth_pos[0],
                self.forth_pos[1],
                z,
                self.forth_pos[3],
                self.forth_pos[4],
                self.forth_pos[5],
            ]),
            vel=self.velx,
            acc=self.accx,
        )
        wait(0.5)

    def rotate_left_for_grip(self):
        movel(
            posx([0, 0, 0, 0, -90, 0]),
            time=10,
            mod=DR_MV_MOD_REL,
        )
        wait(0.5)

    def lower_before_grip(self):
        self.move_relative(dz=-(-10 + self.book_size[2]))

    def grip_book(self):
        self.move_relative(dx=80)
        wait(0.5)

        self.grip_close()
        wait(0.5)

    def lift_book(self):
        self.move_relative(dz=50)
        wait(0.5)

    def tilt_book(self):
        movej(
            posj([0, -60, 0, 0, 0, 0]),
            vel=self.velj,
            acc=self.accj,
            mod=DR_MV_MOD_REL,
        )
        wait(0.5)

    def return_home(self):
        movej(self.first_pos, vel=self.velj, acc=self.accj)
        wait(0.5)

    def run(self):
        self.start_task()

        self.move_to_initial_position()
        self.move_to_return_center_height()
        self.check_height_by_force()
        self.move_to_right_max_position()
        self.lower_by_half_book_thickness()
        self.push_book()

        self.move_above_book()

        self.move_to_left_min_position()
        self.rotate_left_for_grip()
        self.lower_before_grip()
        self.grip_book()
        self.lift_book()
        self.tilt_book()
        self.return_home()


class BookRelease():
    def run(self):
        def close_gripper():
            set_digital_output(1, 0)
            set_digital_output(2, 1)
            wait(3)

        def open_gripper():
            print("open")
            set_digital_output(1, 1)
            set_digital_output(2, 0)
            wait(3)

        def move_joint(pos):
            movej(pos, vel=VELOCITY, acc=ACC)

        def get_current_x():
            return get_current_posx()[0]

        def make_relative_pos(origin, x=0, y=0, z=0):
            return posx(
                origin[0] + x,
                origin[1] + y,
                origin[2] + z,
                origin[3],
                origin[4],
                origin[5],
            )

        def move_relative(x=0, y=0, z=0):
            current = get_current_x()
            target = make_relative_pos(current, x, y, z)
            movel(target, vel=VELOCITY, acc=ACC)

        def compliance_drop():
            # current = get_current_x()
            # target = make_relative_pos(current, z=-25)
            # movel(target, vel=VELOCITY, acc=ACC)
            task_compliance_ctrl()
            set_stiffnessx([200, 200, 20, 100, 100, 100], time=0.5)
            fd = [0, 0, -10, 0, 0, 0]
            fctrl_dir= [0, 0, 1, 0, 0, 0]
            set_desired_force(fd, dir=fctrl_dir, mod=DR_BASE)
            while True:
                f = get_tool_force(DR_BASE)[2]
                print(f)
                if f > 3:
                    break
            release_force()
            wait(0.5)
            r = release_compliance_ctrl()
            if r == 0:
                print("ok")
            else:
                print(r)

        def push_x(distance):
            current = get_current_x()
            current[0] += distance
            movel(current, vel=VELOCITY, acc=ACC)
            compliance_drop()
            open_gripper()
            current = get_current_x()
            current[0] -= distance
            movel(current, vel=VELOCITY, acc=ACC)

        # -------------------------
        # 작업 단위 메서드
        # -------------------------

        def move_to_release_ready():
            move_joint(release_readyj)

        def release_sequence(session_y, session_z):
            move_joint(base)

            close_gripper()

            move_to_release_ready()

            move_relative(y=session_y)
            move_relative(z=session_z)

            push_x(180)

        # -------------------------
        # 위치 정의
        # -------------------------
        base = posj([0.0, 0.0, 90.0, 0.0, 90.0, 0.0])
        release_readyj = posj([-6.000, 11.005, 90.003, -30.003, -14.998, -75.000])

        session_pos = [
            [163, 100],
            [-153, 100],
            [163, -265],
            [-153, -265],
        ]

        # -------------------------
        # 실행
        # -------------------------
        
        y, z = session_pos[session]
        release_sequence(y, z)

        move_joint(base)




robot = BookReturnRobot()
release = BookRelease()
robot.run()
release.run()
"""

