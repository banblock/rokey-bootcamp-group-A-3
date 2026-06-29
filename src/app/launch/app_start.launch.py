from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():

    dsr_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("m0609_rg2_bringup"),
                "launch",
                "bringup.launch.py"
            )
        ),
        launch_arguments={
            "mode": "real",
            "host": "192.168.1.100",
            "port": "12345",
            "model": "m0609"
        }.items(),
    )

    return LaunchDescription([

        dsr_launch,

        Node(
            package="app",
            executable="controller",
            name="controller",
            output="screen",
        ),

        Node(
            package="app",
            executable="ui",
            name="ui",
            output="screen",
        ),

        Node(
            package="app",
            executable="vision",
            name="vision",
            output="screen",
        ),
    ])