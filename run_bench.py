#!/usr/bin/env python

#
# This script is used to run checkpointed images of MARSSx86 Simulator.
# To use this script, make sure that following variables are set correctly:
#   - qemu_bin : Path to the binary 'qemu-system-x86_64' compiled for MARSS
#   - qemu_img : A list of qemu images that contains checkpoints to run.  These
#                images must be identical.  Based on number of images listed,
#                the script will invoke threads to run benchmarks in parallel
#   - vm_smp   : Number of Simulated cores
#   - vnc_counter : Every simulation run its QEMU window in VNC so it can be
#                   accessed later.  By defalt it starts with 10, but change if
#                   other applications are using those vnc servers
#
# Author  : Avadh Patel 
# Contact : apatel at cs.binghamton.edu
#


import os
import subprocess
import sys

workload = sys.argv[1]
from optparse import OptionParser

from threading import Thread, Lock

# First check if user has provided directory to save all results files
opt_parser = OptionParser("Usage: %prog [-d output_dir_name]")
opt_parser.add_option("-d", "--output-dir", dest="output_dir",
        type="string", help="Name of the output directory to save all results")

(options, args) = opt_parser.parse_args()

if options.output_dir == None:
    options.output_dir = "."
else:
    print("Results files will be stored in %s directory" % options.output_dir)
    if not os.path.exists(options.output_dir):
        os.makedirs(options.output_dir)

output_dir = options.output_dir + "/"

# Set up default variables
cwd = os.getcwd()
qemu_bin = '%s/qemu/qemu-system-x86_64' % cwd
# qemu_img = ['/home/avadh/workspace/vm/spec2006.qcow2',
        # '/home/avadh/workspace/vm/spec2006_2.qcow2',
        # '/home/avadh/workspace/vm/spec2006_3.qcow2']
qemu_img = ['%s/../parsec_roi/parsecROI.qcow2' % cwd]
#qemu_imgb = '%s/../parsec_roi/linux-c.raw' % cwd
#qemu_img = ['/home/ibhati/DRAM_MEM/parsec_image/parsec.qcow2']
#vm_memory = 8192
vm_memory = 16384
qemu_cmd = ''
vm_smp = 1
#vm_smp = 2
vnc_counter = 26208

num_threads = len(qemu_img)

# If user give argument 'out' then print the output of simulation run
# to stdout else ignore it
out_to_stdout = False
if len(sys.argv) == 2 and sys.argv[1] == 'out':
    out_to_stdout = True

# Checkpoint list
check_list = []

spec_list = ['perl', 'bzip', 'gcc', 'gamess', 'mcf', 'milc',
        'gromacs', 'cactusADM', 'gobmk', 'deal2', 'soplex', 'povray',
        'calculix', 'hmm', 'quantum', 'tonto', 'omnetpp', 'sphinx', 'xalanc']

parsec_list = ['blackscholes', 'bodytrack', 'ferret', 'freqmine', 'swaptions', 
        'fluidanimate', 'vips', 'x264', 'canneal', 'dedup', 'streamcluster']

# To run single checkpoint
#check_list.append('blackscholes')
#check_list.append('mult-prog')
check_list.append(workload)

# To run all spec checkpoints
# check_list = spec_list

checkpoint_lock = Lock()
checkpoint_iter = iter(check_list)

# Simulation Command
#sim_cmd_generic = 'simconfig -stats %s.stats -run -logfile %s.log'
sim_cmd_generic = 'simconfig -stats %s.stats -run -logfile %s.log -number-of-cores 4 -kill-after-run -stopinsns 1000m -machine shared_l2'
#sim_cmd_generic = 'simconfig -stats %s.stats -run -logfile %s.log -kill-after-run -stopinsns 1000m -machine single_core'
#sim_cmd_generic = 'simulate -stats %s.stats -run -logfile %s.log -stopinsns 10m'

print("Execution command: %s" % qemu_cmd)
print("Generic simulation command: %s" % sim_cmd_generic)
print("Chekcpoints to run: %s" % str(check_list))
print("All files will be saved in: %s" % output_dir)


def pty_to_stdout(fd, untill_chr):
    chr = '1'
    while chr != untill_chr:
        chr = os.read(fd, 1)
        sys.stdout.write(chr)
    sys.stdout.flush()


# Thread class that will store the output on the serial port of qemu to file
class SerialOut(Thread):

    def __init__(self, out_filename, out_devname):
        global output_dir
        super(SerialOut, self).__init__()
        self.out_filename = output_dir + out_filename
        self.out_devname = out_devname

    def run(self):
        # Open the serial port and a file
        out_file = open(self.out_filename, 'w')
        out_dev_file = os.open(self.out_devname, os.O_RDONLY)

        try:
            while True:
                line = os.read(out_dev_file, 1)
                out_file.write(line)
                if len(line) == 0:
                    break
        except OSError:
            pass
            
        print("Writing to output file completed")
        out_file.close()
        os.close(out_dev_file)

# Thread class that will store the output on the serial port of qemu to file
class StdOut(Thread):

    def __init__(self, out_obj_):
        super(StdOut, self).__init__()
        self.out_obj = out_obj_

    def run(self):
        # Open the serial port and a file
        global out_to_stdout
        try:
            while True:
                line = self.out_obj.read(1)
                if len(line) == 0:
                    break
                if out_to_stdout:
                    sys.stdout.write(line)
        except OSError:
            pass
            
        print("Writing to stdout completed")


class RunSim(Thread):

    def __init__(self, qemu_img_name):
        super(RunSim, self).__init__()
        self.qemu_img = qemu_img_name

    def add_to_cmd(self, opt):
        self.qemu_cmd = "%s %s" % (self.qemu_cmd, opt)

    def run(self):
        global checkpoint_lock
        global checkpoint_iter
        global sim_cmd_generic
        global vnc_counter
        global output_dir

        print("Running thread with img: %s" % self.qemu_img)

        # Start simulation from checkpoints
        pty_prefix = 'char device redirected to '
        # for checkpoint in check_list:
        while True:
            checkpoint = None
            self.qemu_cmd = ''

            try:
                checkpoint_lock.acquire()
                checkpoint = checkpoint_iter.next()
                self.vnc_counter = vnc_counter
                vnc_counter += 1
            except:
                checkpoint = None
            finally:
                checkpoint_lock.release()

            if checkpoint == None:
                break
            
            # Generate a common command string
            self.add_to_cmd(qemu_bin)
            self.add_to_cmd('-m %d' % vm_memory)
            self.add_to_cmd('-serial pty')
            self.add_to_cmd('-monitor pty')
            #self.add_to_cmd('-smp %d' % vm_smp)
            self.add_to_cmd('-vnc :%d' % self.vnc_counter)
            #self.add_to_cmd('-cpu core2duo')
            self.add_to_cmd('-S')

            # Add Image at the end
	    #self.add_to_cmd('-hda %s' % self.qemu_img)
	    self.add_to_cmd('-drive cache=unsafe,file=%s' % self.qemu_img)

            print("Starting Checkpoint: %s" % checkpoint)
	    print("qemu command: %s" % self.qemu_cmd)

            p = subprocess.Popen(self.qemu_cmd.split(), stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, bufsize=0)

            monitor_pty = None
            serial_pty = None

            while p.poll() is None:
                line = p.stdout.readline()
                sys.stdout.write(line)
                if line.startswith(pty_prefix):
                    dev_name = line[len(pty_prefix):].strip()

                    # Open the device terminal and send simulation command
                    # pty_term = os.open(dev_name, os.O_RDWR)
                    pty_term = dev_name
                    
                    if monitor_pty == None:
                        monitor_pty = pty_term
                    else :
                        serial_pty = pty_term

                    if monitor_pty != None and serial_pty != None:
                        break

            # Redirect output of serial terminal to file
            serial_thread = SerialOut('%s.out' % (checkpoint), serial_pty)
            
            # os.dup2(serial_pty, sys.stdout.fileno())

            # First load the vm checkpoint
            monitor_pty = os.open(monitor_pty, os.O_RDWR)
            pty_to_stdout(monitor_pty, ")")
            os.write(monitor_pty, "loadvm %s\n" % checkpoint)

            # Send simulation command
            sim_command = sim_cmd_generic % (output_dir + checkpoint, 
                    output_dir + checkpoint)
            pty_to_stdout(monitor_pty, ")")
            os.write(monitor_pty, '%s\n' % sim_command)
            pty_to_stdout(monitor_pty, ")")

            stdout_thread = StdOut(p.stdout)
            stdout_thread.start()
            serial_thread.start()

            # while p.stdout.closed == False:
                # sys.stdout.write(p.stdout.read(128))

            # Wait for simulation to complete
            p.wait()

            serial_thread.join()
            stdout_thread.join()


# Now start RunSim threads
threads = []

for i in range(num_threads):
    th = RunSim(qemu_img[i])
    threads.append(th)
    th.start()

print("All Threads are started")

for th in threads:
    th.join()

print("WoooHooo... Finished Running all Simulations")
print("Wish you get the results you expected :)")
print("See You next time, till then Happy Coding..")


