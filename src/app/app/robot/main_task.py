import rclpy
import DR_init
try:
    from DSR_ROBOT2 import (
        set_tool,
        set_tcp,
        movej,
        movel,
        task_compliance_ctrl,
        set_desired_force,
        get_tool_force,
        release_force,
        release_compliance_ctrl,
        set_digital_output,
        wait,
        get_current_posx,
        set_stiffnessx,
        DR_BASE, DR_FC_MOD_REL,
    )

    from DR_common2 import posx, posj
except ImportError as e:
    print(f"Error importing DSR_ROBOT2 : {e}")

VELOCITY, ACC = 30, 30
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# -------------------------
# 단순화 메서드
# -------------------------

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

# -------------------------
# 작업 단위 메서드
# -------------------------

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

def prepare_robot():
    set_tool("Tool Weight1")
    set_tcp("GripperDA_v2")


def main_task():

    # -------------------------
    # 변수 정의
    # -------------------------

    release_base = posj([0.0, 0.0, 90.0, 0.0, 90.0, 0.0])
    release_readyj = posj([-6.000, 11.005, 90.003, -30.003, -14.998, -75.000])

    session_pos = [
        [163, 100],
        [-153, 100],
        [163, -265],
        [-153, -265],
    ]
    # -------------------------
    # sequence 정의
    # -------------------------

    def release_sequence(session_y, session_z):
        move_joint(release_base)

        close_gripper()

        move_joint(release_readyj)

        move_relative(y=session_y)
        move_relative(z=session_z)

        push_x(180)
    # -------------------------
    # 실행
    # -------------------------

    prepare_robot()

    open_gripper()

    for y, z in session_pos:
        release_sequence(y, z)

    move_joint(release_base)