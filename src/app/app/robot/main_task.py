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
        DR_BASE, DR_FC_MOD_REL,
    )

    from DR_common2 import posx, posj
except ImportError as e:
    print(f"Error importing DSR_ROBOT2 : {e}")

VELOCITY, ACC = 30, 30
def main_task():

    def reset(pos):
        movej(pos, vel=VELOCITY, acc=ACC)

    def force_down():
        force_d = [0,0,-20,0,0,0]
        force_dir = [0,0,1,0,0,0]
        task_compliance_ctrl([3000,3000,3000,200,200,200])
        wait(0.5)
        set_desired_force(force_d, dir=force_dir, mod=DR_FC_MOD_REL)
        wait(0.5)

        while True:
            f = get_tool_force(DR_BASE)[2]
            print('in')
            if f > 10:
                break
        
        release_force()
        wait(0.5)
        release_compliance_ctrl()
        wait(0.5)

    def check_top():
        set_digital_output(1,0)
        set_digital_output(2,1)
        wait(3)
        force_down()
        a = get_current_posx()[0]
        a[2] += 10
        movel(a,vel=VELOCITY, acc=ACC)



    set_tool("Tool Weight")
    set_tcp("GripperDA_v1")

    base = posj([0.0, 0.0, 90.0, 0.0, 90.0, 0.0])
    grap_ready = posj([90.0, 0.0, 90.0, 0.0, 90.0, 0.0])
    top_entry = posx([66.28, 44.16, 9.99, -0.34, 125.86, 65.98])
    movej(base, vel=VELOCITY, acc=ACC)
    reset(grap_ready, vel=VELOCITY, acc=ACC)
    movel(top_entry)
    check_top()