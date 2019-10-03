#! /usr/bin/env python

"""
Tools for creating URScript messages, for communicating with the real UR
robots over TCP/IP by creating URScript programs and sending them for
execution on the robot's system

built off of urscript.py, part of python-urx library
(https://github.com/anthonysimeonov/python-urx/blob/master/urx/urscript.py)
"""

import logging

# Controller Settings
CONTROLLER_PORTS = [0, 1]
CONTROLLER_VOLTAGE = [
    0,  # 0-5V
    2,  # 0-10V
]

# Tool Settings
TOOL_PORTS = [2, 3]
TOOL_VOLTAGE = [
    0,  # 0-5V
    1,  # 0-10V
    2,  # 4-20mA
]

OUTPUT_DOMAIN_VOLTAGE = [
    0,  # 4-20mA
    1,  # 0-10V
]


class URScript(object):

    def __init__(self):
        self.logger = logging.getLogger(u"urscript")
        # The header is code that is before and outside the myProg() method
        self.header = ""
        # The program is code inside the myProg() method
        self.program = ""

    def __call__(self):
        if self.program == "":
            self.logger.debug(u"urscript program is empty")
            return ""

        # Construct the program
        myprog = """def myProg():{}\nend""".format(self.program)

        # Construct the full script
        script = ""
        if self.header:
            script = "{}\n\n".format(self.header)
        script = "{}{}".format(script, myprog)
        return script

    def reset(self):
        self.header = ""
        self.program = ""

    def _add_header_to_program(self, header_line):
        self.header = "{}\n{}".format(self.header, header_line)

    def _add_line_to_program(self, new_line):
        self.program = "{}\n\t{}".format(self.program, new_line)

    def constrain_unsigned_char(self, value):
        """
        Ensure that unsigned char values are constrained
        to between 0 and 255.
        """
        assert (isinstance(value, int))
        if value < 0:
            value = 0
        elif value > 255:
            value = 255
        return value

    def sleep(self, value):
        msg = "sleep({})".format(value)
        self._add_line_to_program(msg)

    def socket_open(self, socket_host, socket_port, socket_name):
        msg = "socket_open(\"{}\",{},\"{}\")".format(socket_host,
                                                     socket_port,
                                                     socket_name)
        self._add_line_to_program(msg)

    def socket_close(self, socket_name):
        msg = "socket_close(\"{}\")".format(socket_name)
        self._add_line_to_program(msg)

    def socket_get_var(self, var, socket_name):
        msg = "socket_get_var(\"{}\",\"{}\")".format(var, socket_name)
        self._add_line_to_program(msg)
        self.sync()

    def socket_set_var(self, var, value, socket_name):
        msg = "socket_set_var(\"{}\",{},\"{}\")".format(
            var,
            value,
            socket_name)
        self._add_line_to_program(msg)
        self.sync()

    def socket_read_byte_list(self, nbytes, socket_name):
        msg = "global var_value = socket_read_byte_list({},\"{}\")".format(
            nbytes,
            socket_name)
        self._add_line_to_program(msg)
        self.sync()

    def socket_send_string(self, message, socket_name):
        msg = "socket_send_string(\"{}\",\"{}\")".format(
            message,
            socket_name)
        self._add_line_to_program(msg)
        self.sync()

    def sync(self):
        msg = "sync()"
        self._add_line_to_program(msg)


class Robotiq2F140URScript(URScript):
    """
    Class for creating Robotiq 2F140 specific URScript
    messages to send to the UR robot, for setting gripper
    related variables
    """
    def __init__(self,
                 socket_host,
                 socket_port,
                 socket_name):
        self.socket_host = socket_host
        self.socket_port = socket_port
        self.socket_name = socket_name
        super(Robotiq2F140URScript, self).__init__()

        # reset gripper connection
        self.socket_close(self.socket_name)
        self.socket_open(
            self.socket_host,
            self.socket_port,
            self.socket_name
        )

    def set_activate(self):
        """
        Activate the gripper, by setting some internal
        variables on the UR controller to 1
        """
        self.socket_set_var('ACT', 1, self.socket_name)

    def set_gripper_position(self, position):
        """
        Control the gripper position by setting internal
        position variable to desired position value on
        UR controller

        Args:
            position (int): Position value, ranges from 0-255
        """
        position = self.constrain_unsigned_char(position)
        self.socket_set_var('POS', position, self.socket_name)

    def set_gripper_speed(self, speed):
        """
        Set what speed the gripper should move

        Args:
            speed (int): Desired gripper speed, ranges from 0-255
        """
        speed = self.constrain_unsigned_char(speed)
        self.socket_set_var('SPE', speed, self.socket_name)

    def set_gripper_force(self, force):
        """
        Set maximum gripper force

        Args:
            force (int): Desired maximum gripper force, ranges
                from 0-255
        """
        force = self.constrain_unsigned_char(force)
        self.socket_set_var('FOR', force, self.socket_name)
