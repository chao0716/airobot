from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import copy

import numpy as np
import pybullet as p
from gym.utils import seeding

import airobot.utils.common as arutil
from airobot.arm.arm import ARM
from airobot.utils.arm_util import wait_to_reach_jnt_goal
from airobot.utils.pb_util import PB_CLIENT
from airobot.utils.pb_util import set_step_sim


class SingleArmPybullet(ARM):
    """
    Class for the pybullet simulation environment
    of a UR5e robot with a robotiq 2f140 gripper.

    """

    def __init__(self, cfgs, render=False, seed=None,
                 rt_simulation=True, self_collision=False,
                 eetool_cfg=None):
        """
        Constructor for the pybullet simulation environment
        of a UR5e robot with a robotiq 2f140 gripper

        Args:
            cfgs (YACS CfgNode): configurations for the arm
            render (bool): whether to render the environment using GUI
            seed (int): random seed
            rt_simulation (bool): turn on realtime simulation or not
            self_collision (bool): enable self_collision or
                                   not whiling loading URDF
            eetool_cfg (dict): arguments to pass in the constructor
                of the end effector tool class
        """

        self._render = render
        self.self_collision = self_collision
        super(SingleArmPybullet, self).__init__(cfgs=cfgs,
                                                eetool_cfg=eetool_cfg)
        self.p = p
        self.robot_id = None
        self.np_random, _ = self._seed(seed)

        self._init_consts()
        self.realtime_simulation(rt_simulation)
        self._in_torque_mode = [False] * self.arm_dof

    @property
    def joint_names(self):
        """
        Return the joint names in urdf

        Returns:
            list: joint names
        """
        return list(self.jnt_to_id.keys())

    def go_home(self, ignore_physics=False):
        """
        Move the robot to a pre-defined home pose
        """
        success = self.set_jpos(self._home_position,
                                ignore_physics=ignore_physics)
        return success

    def reset(self):
        """
        Reset the simulation environment.
        """
        self.robot_id = self.p.loadURDF(self.cfgs.PYBULLET_URDF,
                                        [0, 0, 0], [0, 0, 0, 1],
                                        physicsClientId=PB_CLIENT)

    def realtime_simulation(self, on=True):
        """
        Turn on/off the realtime simulation mode

        Args:
            on (bool): run the simulation in realtime if True
                stop the realtime simulation if False
        """
        self._step_sim_mode = not on
        if self.cfgs.HAS_EETOOL:
            self.eetool._step_sim_mode = self._step_sim_mode
        set_step_sim(self._step_sim_mode)

    def set_jpos(self, position, joint_name=None,
                 wait=True, ignore_physics=False, *args, **kwargs):
        """
        Move the arm to the specified joint position(s).

        Args:
            position (float or list): desired joint position(s)
            joint_name (str): If not provided, position should be a list
                and all the actuated joints will be moved to the specified
                positions. If provided, only the specified joint will
                be moved to the desired joint position
            wait (bool): whether to block the code and wait
                for the action to complete
            ignore_physics (bool): hard reset the joints to the target joint
                positions. It's best only to do this at the start,
                while not running the simulation. It will overrides
                all physics simulation.

        Returns:
            bool: A boolean variable representing if the action is successful
            at the moment when the function exits
        """
        position = copy.deepcopy(position)
        success = False
        if joint_name is None:
            if len(position) != self.arm_dof:
                raise ValueError('Position should contain %d'
                                 'elements if the joint_name'
                                 ' is not provided' % self.arm_dof)
            tgt_pos = position
            if ignore_physics:
                # we need to set the joints to velocity control mode
                # so that the reset takes effect. Otherwise, the joints
                # will just go back to the original positions
                self.set_jvel([0.] * self.arm_dof)
                for idx, jnt in enumerate(self.arm_jnt_names):
                    self.reset_joint_state(
                        jnt,
                        tgt_pos[idx]
                    )
                success = True
            else:
                self.p.setJointMotorControlArray(self.robot_id,
                                                 self.arm_jnt_ids,
                                                 self.p.POSITION_CONTROL,
                                                 targetPositions=tgt_pos,
                                                 forces=self._max_torques,
                                                 physicsClientId=PB_CLIENT)
        else:
            if joint_name not in self.arm_jnt_names_set:
                raise TypeError('Joint name [%s] is not in the arm'
                                ' joint list!' % joint_name)
            else:
                tgt_pos = position
                arm_jnt_idx = self.arm_jnt_names.index(joint_name)
                max_torque = self._max_torques[arm_jnt_idx]
                jnt_id = self.jnt_to_id[joint_name]
            if ignore_physics:
                self.set_jvel(0., joint_name)
                self.reset_joint_state(joint_name, tgt_pos)
                success = True
            else:
                self.p.setJointMotorControl2(self.robot_id,
                                             jnt_id,
                                             self.p.POSITION_CONTROL,
                                             targetPosition=tgt_pos,
                                             force=max_torque,
                                             physicsClientId=PB_CLIENT)
        if not self._step_sim_mode and wait and not ignore_physics:
            success = wait_to_reach_jnt_goal(
                tgt_pos,
                get_func=self.get_jpos,
                joint_name=joint_name,
                get_func_derv=self.get_jvel,
                timeout=self.cfgs.ARM.TIMEOUT_LIMIT,
                max_error=self.cfgs.ARM.MAX_JOINT_ERROR
            )
        return success

    def set_jvel(self, velocity, joint_name=None, wait=False, *args, **kwargs):
        """
        Move the arm with the specified joint velocity(ies).

        Args:
            velocity (float or list): desired joint velocity(ies)
            joint_name (str): If not provided, velocity should be a list
                and all the actuated joints will be moved in the specified
                velocities. If provided, only the specified joint will
                be moved in the desired joint velocity
            wait (bool): whether to block the code and wait
                for the action to complete

        Returns:
            bool: A boolean variable representing if the action is successful
            at the moment when the function exits
        """
        velocity = copy.deepcopy(velocity)
        success = False
        if joint_name is None:
            velocity = copy.deepcopy(velocity)
            if len(velocity) != self.arm_dof:
                raise ValueError('Velocity should contain %d elements '
                                 'if the joint_name is not '
                                 'provided' % self.arm_dof)
            tgt_vel = velocity
            self.p.setJointMotorControlArray(self.robot_id,
                                             self.arm_jnt_ids,
                                             self.p.VELOCITY_CONTROL,
                                             targetVelocities=tgt_vel,
                                             forces=self._max_torques,
                                             physicsClientId=PB_CLIENT)
        else:
            if joint_name not in self.arm_jnt_names_set:
                raise TypeError('Joint name [%s] is not in the arm'
                                ' joint list!' % joint_name)
            else:
                tgt_vel = velocity
                arm_jnt_idx = self.arm_jnt_names.index(joint_name)
                max_torque = self._max_torques[arm_jnt_idx]
                jnt_id = self.jnt_to_id[joint_name]
            self.p.setJointMotorControl2(self.robot_id,
                                         jnt_id,
                                         self.p.VELOCITY_CONTROL,
                                         targetVelocity=tgt_vel,
                                         force=max_torque,
                                         physicsClientId=PB_CLIENT)
        if not self._step_sim_mode:
            if wait:
                success = wait_to_reach_jnt_goal(
                    tgt_vel,
                    get_func=self.get_jvel,
                    joint_name=joint_name,
                    timeout=self.cfgs.ARM.TIMEOUT_LIMIT,
                    max_error=self.cfgs.ARM.MAX_JOINT_VEL_ERROR
                )
            else:
                success = True
        return success

    def set_jtorq(self, torque, joint_name=None, wait=False, *args, **kwargs):
        """
        Apply torque(s) to the joint(s), call enable_torque_control()
        or enable_torque_control(joint_name) before doing torque control.

        Note:
            call to this function is only effective in this simulation step.
            you need to supply torque value for each simulation step to do
            the torque control. It's easier to use torque control
            in step_simulation mode instead of realtime_simulation mode.
            If you are using realtime_simulation mode, the time interval
            between two set_jtorq() calls must be small enough (like 0.0002s)

        Args:
            torque (float or list): torque value(s) for the joint(s)
            joint_name (str): specify the joint on which the torque is applied.
                If it's not provided(None), it will apply the torques on
                the six joints on the arm. Otherwise, only the specified joint
                will be applied with the given torque.
            wait (bool): Not used in this method, just
                to keep the method signature consistent

        Returns:
            bool: Always return True as the torque will be applied as specified
            in Pybullet

        """
        torque = copy.deepcopy(torque)
        if not self._is_in_torque_mode(joint_name):
            raise RuntimeError('Call \'enable_torque_control\' first'
                               ' before setting torque(s)')
        if joint_name is None:
            if len(torque) != self.arm_dof:
                raise ValueError('Joint torques should contain'
                                 ' %d elements' % self.arm_dof)
            self.p.setJointMotorControlArray(self.robot_id,
                                             self.arm_jnt_ids,
                                             self.p.TORQUE_CONTROL,
                                             forces=torque,
                                             physicsClientId=PB_CLIENT)
        else:
            if joint_name not in self.arm_jnt_names_set:
                raise ValueError('Only torque control on'
                                 ' the arm is supported!')
            jnt_id = self.jnt_to_id[joint_name]
            self.p.setJointMotorControl2(self.robot_id,
                                         jnt_id,
                                         self.p.TORQUE_CONTROL,
                                         force=torque,
                                         physicsClientId=PB_CLIENT)
        return True

    def set_ee_pose(self, pos=None, ori=None, wait=True, *args, **kwargs):
        """
        Move the end effector to the specifed pose

        Args:
            pos (list or np.ndarray): Desired x, y, z positions in the robot's
                base frame to move to (shape: :math:`[3,]`)
            ori (list or np.ndarray, optional): It can be euler angles
                ([roll, pitch, yaw], shape: :math:`[4,]`),
                or quaternion ([qx, qy, qz, qw], shape: :math:`[4,]`),
                or rotation matrix (shape: :math:`[3, 3]`). If it's None,
                the solver will use the current end effector
                orientation as the target orientation

        Returns:
            bool: A boolean variable representing if the action is successful
            at the moment when the function exits
        """
        if pos is None:
            pose = self.get_ee_pose()
            pos = pose[0]
        jnt_pos = self.compute_ik(pos, ori)
        success = self.set_jpos(jnt_pos, wait=wait)
        return success

    def move_ee_xyz(self, delta_xyz, eef_step=0.005, *args, **kwargs):
        """
        Move the end-effector in a straight line without changing the
        orientation

        Args:
            delta_xyz (list or np.ndarray): movement in x, y, z
                directions (shape: :math:`[3,]`)
            eef_step (float): interpolation interval along delta_xyz.
                Interpolate a point every eef_step distance
                between the two end points

        Returns:
            bool: A boolean variable representing if the action is successful
            at the moment when the function exits
        """
        if self._step_sim_mode:
            raise AssertionError('move_ee_xyz() can '
                                 'only be called in realtime'
                                 ' simulation mode')
        pos, quat, rot_mat, euler = self.get_ee_pose()
        cur_pos = np.array(pos)
        delta_xyz = np.array(delta_xyz)

        waypoints = arutil.linear_interpolate_path(cur_pos,
                                                   delta_xyz,
                                                   eef_step)
        way_jnt_positions = []
        for i in range(waypoints.shape[0]):
            tgt_jnt_poss = self.compute_ik(waypoints[i, :].flatten().tolist(),
                                           quat)
            way_jnt_positions.append(copy.deepcopy(tgt_jnt_poss))
        success = False
        for jnt_poss in way_jnt_positions:
            success = self.set_jpos(jnt_poss)
        return success

    def enable_torque_control(self, joint_name=None):
        """
        Enable the torque control mode in Pybullet

        Args:
            joint_name (str): If it's none, then all the six joints
                on the UR robot are enabled in torque control mode.
                Otherwise, only the specified joint is enabled
                in torque control mode.

        """
        if joint_name is None:
            tgt_vels = [0.0] * self.arm_dof
            forces = [0.0] * self.arm_dof
            self.p.setJointMotorControlArray(self.robot_id,
                                             self.arm_jnt_ids,
                                             self.p.VELOCITY_CONTROL,
                                             targetVelocities=tgt_vels,
                                             forces=forces,
                                             physicsClientId=PB_CLIENT)
            self._in_torque_mode = [True] * self.arm_dof
        else:
            jnt_id = self.jnt_to_id[joint_name]
            self.p.setJointMotorControl2(self.robot_id,
                                         jnt_id,
                                         self.p.VELOCITY_CONTROL,
                                         targetVelocity=0,
                                         force=0.0,
                                         physicsClientId=PB_CLIENT)
            arm_jnt_id = self.arm_jnt_names.index(joint_name)
            self._in_torque_mode[arm_jnt_id] = True

    def disable_torque_control(self, joint_name=None):
        """
        Disable the torque control mode in Pybullet

        Args:
            joint_name (str): If it's none, then all the six joints
                on the UR robot are disabled with torque control.
                Otherwise, only the specified joint is disabled with
                torque control.
                The joint(s) will enter velocity control mode.

        """
        if joint_name is None:
            self.set_jvel([0.0] * self.arm_dof)
            self._in_torque_mode = [False] * self.arm_dof
        else:
            self.set_jvel(0.0, joint_name)
            arm_jnt_id = self.arm_jnt_names.index(joint_name)
            self._in_torque_mode[arm_jnt_id] = False

    def get_jpos(self, joint_name=None):
        """
        Return the joint position(s) of the arm

        Args:
            joint_name (str, optional): If it's None,
                it will return joint positions
                of all the actuated joints. Otherwise, it will
                return the joint position of the specified joint

        Returns:
            One of the following

            - float: joint position given joint_name
            - list: joint positions if joint_name is None
              (shape: :math:`[DOF]`)
        """
        if joint_name is None:
            states = self.p.getJointStates(self.robot_id,
                                           self.arm_jnt_ids,
                                           physicsClientId=PB_CLIENT)
            pos = [state[0] for state in states]
        else:
            jnt_id = self.jnt_to_id[joint_name]
            pos = self.p.getJointState(self.robot_id,
                                       jnt_id,
                                       physicsClientId=PB_CLIENT)[0]
        return pos

    def get_jvel(self, joint_name=None):
        """
        Return the joint velocity(ies) of the arm

        Args:
            joint_name (str, optional): If it's None, it will return
                joint velocities of all the actuated joints. Otherwise,
                it will return the joint velocity of the specified joint

        Returns:
            One of the following

            - float: joint velocity given joint_name
            - list: joint velocities if joint_name is None
              (shape: :math:`[DOF]`)
        """
        if joint_name is None:
            states = self.p.getJointStates(self.robot_id,
                                           self.arm_jnt_ids,
                                           physicsClientId=PB_CLIENT)
            vel = [state[1] for state in states]
        else:
            jnt_id = self.jnt_to_id[joint_name]
            vel = self.p.getJointState(self.robot_id,
                                       jnt_id,
                                       physicsClientId=PB_CLIENT)[1]
        return vel

    def get_jtorq(self, joint_name=None):
        """
        If the robot is operated in VELOCITY_CONTROL or POSITION_CONTROL mode,
        return the joint torque(s) applied during the last simulation step. In
        TORQUE_CONTROL, the applied joint motor torque is exactly what
        you provide, so there is no need to report it separately.
        So don't use this method to get the joint torque values when
        the robot is in TORQUE_CONTROL mode.

        Args:
            joint_name (str, optional): If it's None,
                it will return joint torques
                of all the actuated joints. Otherwise, it will
                return the joint torque of the specified joint

        Returns:
            One of the following

            - float: joint torque given joint_name
            - list: joint torques if joint_name is None
              (shape: :math:`[DOF]`)
        """
        if joint_name is None:
            states = self.p.getJointStates(self.robot_id,
                                           self.arm_jnt_ids,
                                           physicsClientId=PB_CLIENT)
            # state[3] is appliedJointMotorTorque
            torque = [state[3] for state in states]
        else:
            jnt_id = self.jnt_to_id[joint_name]
            torque = self.p.getJointState(self.robot_id,
                                          jnt_id,
                                          physicsClientId=PB_CLIENT)[3]
        return torque

    def get_ee_pose(self):
        """
        Return the end effector pose

        Returns:
            4-element tuple containing

            - np.ndarray: x, y, z position of the EE (shape: :math:`[3,]`)
            - np.ndarray: quaternion representation of the
              EE orientation (shape: :math:`[4,]`)
            - np.ndarray: rotation matrix representation of the
              EE orientation (shape: :math:`[3, 3]`)
            - np.ndarray: euler angle representation of the
              EE orientation (roll, pitch, yaw with
              static reference frame) (shape: :math:`[3,]`)
        """
        info = self.p.getLinkState(self.robot_id, self.ee_link_id,
                                   physicsClientId=PB_CLIENT)
        pos = info[4]
        quat = info[5]

        rot_mat = arutil.quat2rot(quat)
        euler = arutil.quat2euler(quat, axes='xyz')  # [roll, pitch, yaw]
        return np.array(pos), np.array(quat), rot_mat, euler

    def get_ee_vel(self):
        """
        Return the end effector's velocity

        Returns:
            2-element tuple containing

            - np.ndarray: translational velocity (shape: :math:`[3,]`)
            - np.ndarray: rotational velocity (shape: :math:`[3,]`)
        """
        info = self.p.getLinkState(self.robot_id,
                                   self.ee_link_id,
                                   computeLinkVelocity=1,
                                   physicsClientId=PB_CLIENT)
        trans_vel = info[6]
        rot_vel = info[7]
        return np.array(trans_vel), np.array(rot_vel)

    def compute_ik(self, pos, ori=None, *args, **kwargs):
        """
        Compute the inverse kinematics solution given the
        position and orientation of the end effector

        Args:
            pos (list or np.ndarray): position (shape: :math:`[3,]`)
            ori (list or np.ndarray): orientation. It can be euler angles
                ([roll, pitch, yaw], shape: :math:`[3,]`), or
                quaternion ([qx, qy, qz, qw], shape: :math:`[4,]`),
                or rotation matrix (shape: :math:`[3, 3]`).

        Returns:
            list: solution to inverse kinematics, joint angles which achieve
            the specified EE pose (shape: :math:`[DOF]`)
        """
        ex_args = {'jointDamping': self._ik_jds,
                   'physicsClientId': PB_CLIENT}
        if ori is not None:
            ori = arutil.to_quat(ori)
            jnt_poss = self.p.calculateInverseKinematics(self.robot_id,
                                                         self.ee_link_id,
                                                         pos,
                                                         ori,
                                                         **ex_args)
        else:
            jnt_poss = self.p.calculateInverseKinematics(self.robot_id,
                                                         self.ee_link_id,
                                                         pos,
                                                         **ex_args)
        jnt_poss = list(jnt_poss)
        return jnt_poss[:self.arm_dof]

    def reset_joint_state(self, jnt_name, jpos, jvel=0):
        """
        Reset the state of the joint. It's best only to do
        this at the start, while not running the simulation.
        It will overrides all physics simulation.

        Args:
            jnt_name (str): joint name
            jpos (float): target joint position
            jvel (float): optional, target joint velocity

        """
        p.resetJointState(self.robot_id,
                          self.jnt_to_id[jnt_name],
                          targetValue=jpos,
                          targetVelocity=jvel,
                          physicsClientId=PB_CLIENT)

    def _is_in_torque_mode(self, joint_name=None):
        if joint_name is None:
            return all(self._in_torque_mode)
        else:
            jnt_id = self.arm_jnt_names.index(joint_name)
            return self._in_torque_mode[jnt_id]

    def _seed(self, seed=None):
        np_random, seed = seeding.np_random(seed)
        return np_random, seed

    def _init_consts(self):
        """
        Initialize constants
        """
        self._home_position = self.cfgs.ARM.HOME_POSITION
        # joint damping for inverse kinematics
        self._ik_jd = 0.0005
        self.arm_jnt_names = self.cfgs.ARM.JOINT_NAMES

        self.arm_jnt_names_set = set(self.arm_jnt_names)
        self.arm_dof = len(self.arm_jnt_names)
        self.rvl_joint_names = self.arm_jnt_names + self.eetool.jnt_names
        self._ik_jds = [self._ik_jd] * len(self.rvl_joint_names)
        self.ee_link_jnt = self.cfgs.ARM.ROBOT_EE_FRAME_JOINT

        self._max_torques = self.cfgs.ARM.MAX_TORQUES

    def _build_jnt_id(self):
        """
        Build the mapping from the joint name to joint index
        """
        self.jnt_to_id = {}
        for i in range(self.p.getNumJoints(self.robot_id,
                                           physicsClientId=PB_CLIENT)):
            info = self.p.getJointInfo(self.robot_id, i,
                                       physicsClientId=PB_CLIENT)
            jnt_name = info[1].decode('UTF-8')
            self.jnt_to_id[jnt_name] = info[0]

        self.ee_link_id = self.jnt_to_id[self.ee_link_jnt]
        self.arm_jnt_ids = [self.jnt_to_id[jnt] for jnt in self.arm_jnt_names]
