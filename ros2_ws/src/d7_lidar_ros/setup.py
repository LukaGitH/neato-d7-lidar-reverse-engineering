from setuptools import find_packages, setup

package_name = "d7_lidar_ros"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "pyserial"],
    zip_safe=True,
    maintainer="LukaGitH",
    maintainer_email="LukaGitH@users.noreply.github.com",
    description="ROS2 LaserScan publisher for the Neato Botvac D7 LiDAR.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "d7_lidar_scan = d7_lidar_ros.lidar_scan_node:main",
        ],
    },
)
