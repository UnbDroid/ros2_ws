from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def generate_launch_description():

    use_sim_time = LaunchConfiguration('use_sim_time')
    params_file = LaunchConfiguration('params_file')

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock',
    )

    declare_params_file = DeclareLaunchArgument(
        'params_file',
        default_value='/home/droid/nav2_config/nav2_params.yaml',
        description='Full path to the Nav2 parameters file',
    )

    params = [params_file, {'use_sim_time': use_sim_time}]

    tf_remappings = [
        ('/tf', 'tf'),
        ('/tf_static', 'tf_static'),
    ]

    # --------------------------------------------------
    # Servidores do Nav2 como componentes.
    # Todos rodam dentro de UM processo (o container), o que deixa
    # a descoberta do DDS bem mais leve e economiza CPU/RAM na Pi.
    #
    # Removidos em relação à versão anterior:
    #   - smoother_server   (só é usado se o BT tiver o nó SmoothPath)
    #   - waypoint_follower (só é usado para seguir vários waypoints)
    # --------------------------------------------------

    composable_nodes = [

        # Controller Server + Local Costmap -> publica em /cmd_vel_nav
        ComposableNode(
            package='nav2_controller',
            plugin='nav2_controller::ControllerServer',
            name='controller_server',
            parameters=params,
            remappings=tf_remappings + [('cmd_vel', 'cmd_vel_nav')],
        ),

        # Planner Server + Global Costmap
        ComposableNode(
            package='nav2_planner',
            plugin='nav2_planner::PlannerServer',
            name='planner_server',
            parameters=params,
            remappings=tf_remappings,
        ),

        # Behaviors / recoveries (spin, backup, wait) -> /cmd_vel_nav
        ComposableNode(
            package='nav2_behaviors',
            plugin='behavior_server::BehaviorServer',
            name='behavior_server',
            parameters=params,
            remappings=tf_remappings + [('cmd_vel', 'cmd_vel_nav')],
        ),

        # Behavior Tree Navigator
        ComposableNode(
            package='nav2_bt_navigator',
            plugin='nav2_bt_navigator::BtNavigator',
            name='bt_navigator',
            parameters=params,
            remappings=tf_remappings,
        ),

        # Velocity Smoother: /cmd_vel_nav -> /cmd_vel_smoothed (saída pelo YAML)
        ComposableNode(
            package='nav2_velocity_smoother',
            plugin='nav2_velocity_smoother::VelocitySmoother',
            name='velocity_smoother',
            parameters=params,
            remappings=tf_remappings + [('cmd_vel', 'cmd_vel_nav')],
        ),

        # Collision Monitor: /cmd_vel_smoothed -> /cmd_vel (tópicos pelo YAML)
        #
        # Para REMOVER o collision monitor e economizar mais CPU:
        #   1. apague este ComposableNode e o 'collision_monitor' de lifecycle_nodes;
        #   2. no velocity_smoother acima, adicione ('cmd_vel_smoothed', 'cmd_vel')
        #      aos remappings, para o comando chegar direto no robô.
        ComposableNode(
            package='nav2_collision_monitor',
            plugin='nav2_collision_monitor::CollisionMonitor',
            name='collision_monitor',
            parameters=params,
            remappings=tf_remappings,
        ),

        # Lifecycle Manager
        ComposableNode(
            package='nav2_lifecycle_manager',
            plugin='nav2_lifecycle_manager::LifecycleManager',
            name='lifecycle_manager_navigation',
            parameters=[{
                'use_sim_time': use_sim_time,
                'autostart': True,
                'node_names': [
                    'controller_server',
                    'planner_server',
                    'behavior_server',
                    'velocity_smoother',
                    'collision_monitor',
                    'bt_navigator',
                ],
                # Antes: 4 s sem heartbeat derrubava tudo.
                # Agora um soluço de CPU de alguns segundos não mata o Nav2.
                'bond_timeout': 10.0,
                'attempt_respawn_reconnection': True,
            }],
        ),
    ]

    # component_container_isolated: cada servidor ganha sua própria
    # thread de execução, então um servidor ocupado não trava o
    # heartbeat dos outros.
    nav2_container = ComposableNodeContainer(
        name='nav2_container',
        namespace='',
        package='rclcpp_components',
        executable='component_container_isolated',
        # O YAML precisa ir para o CONTAINER também: assim ele vale para
        # todos os nós do processo, inclusive os sub-nós local_costmap e
        # global_costmap (que não recebem os parâmetros do ComposableNode).
        parameters=params,
        composable_node_descriptions=composable_nodes,
        output='screen',
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_params_file,
        nav2_container,
    ])
