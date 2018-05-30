import os
import sys
import argparse
import param
import shlex
import subprocess
import multiprocessing
from threading import Thread
import signal
import random
import time

chroms = {"chr"+str(i) for i in range(1,23)}.union(str(i) for i in range(1,23)).union(["X","Y","chrX","chrY"])

class InstancesClass(object):
    def __init__(self):
        self.init()

    def init(self):
        self.GTInstance = None
        self.CTSInstance = None
        self.VVInstance = None

    def poll(self):
        self.GTInstance.poll()
        self.CTSInstance.poll()
        self.VVInstance.poll()
c = InstancesClass();


def CheckRtCode(signum, frame):
    c.poll()
    #print >> sys.stderr, c.GTInstance.returncode, c.CTSInstance.returncode, c.VVInstance.returncode
    if c.GTInstance.returncode != None and c.GTInstance.returncode != 0:
        c.CTSInstance.kill(); c.VVInstance.kill()
        sys.exit("GetTruth.py exited with exceptions. Exiting...");

    if c.CTSInstance.returncode != None and c.CTSInstance.returncode != 0:
        c.GTInstance.kill(); c.VVInstance.kill()
        sys.exit("CreateTensorsSites.py exited with exceptions. Exiting...");

    if c.VVInstance.returncode != None and c.VVInstance.returncode != 0:
        c.GTInstance.kill(); c.CTSInstance.kill()
        sys.exit("clairvoyante_test.py exited with exceptions. Exiting...");

    if c.GTInstance.returncode == None or c.CTSInstance.returncode == None or c.VVInstance.returncode == None:
        signal.alarm(5)


def CheckFileExist(fn, sfx=""):
    if not os.path.isfile(fn+sfx):
        sys.exit("Error: %s not found" % (fn+sfx))
    return os.path.abspath(fn)


def CheckCmdExist(cmd):
    try:
        subprocess.check_output("which %s" % (cmd), shell=True)
    except:
        return -1
    return cmd


def Run(args):
    # --------------------------------------- Parameter check
    basedir = os.path.dirname(__file__)
    GTBin = CheckFileExist(basedir + "/../dataPrepScripts/GetTruth.py")
    CTSBin = CheckFileExist(basedir + "/../dataPrepScripts/CreateTensorSites.py")
    VVBin = CheckFileExist(basedir + "/clairvoyante_test.py")
    pypyBin = CheckCmdExist(args.pypy)
    if pypyBin == -1 : pypyBin = "python"
    samtoolsBin = CheckCmdExist(args.samtools)
    if samtoolsBin == -1 : sys.exit("samtools not found")
    chkpnt_fn = CheckFileExist(args.chkpnt_fn, sfx=".meta")
    bam_fn = CheckFileExist(args.bam_fn)
    ref_fn = CheckFileExist(args.ref_fn)
    vcf_fn = CheckFileExist(args.vcf_fn)
    val_fn = args.val_fn
    sampleName = args.sampleName
    dcov = args.dcov

    maxCpus = multiprocessing.cpu_count()
    if args.threads == None: numCpus = multiprocessing.cpu_count()
    else: numCpus = args.threads if args.threads < multiprocessing.cpu_count() else multiprocessing.cpu_count()
    cpuSet = ",".join(str(x) for x in random.sample(xrange(0, maxCpus), numCpus))
    taskSet = "taskset -c %s"
    try:
        subprocess.check_output("which %s" % (taskset), shell=True)
    except:
        taskSet = ""
    # ---------------------------------------

    # --------------------------------------- Divide VCF into choromosomes, then process
    def RunOnACtg(ctgName, inputs, outputs):
        try:
            c.init()
            c.GTInstance = subprocess.Popen(\
                shlex.split("%s %s --ctgName %s" %\
                            (pypyBin, GTBin, ctgName) ),\
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, bufsize=8388608)
            c.CTSInstance = subprocess.Popen(\
                shlex.split("%s %s --bam_fn %s --ref_fn %s --ctgName %s --samtools %s --dcov %d" %\
                            (pypyBin, CTSBin, bam_fn, ref_fn, ctgName, samtoolsBin, dcov) ),\
                            stdin=c.GTInstance.stdout, stdout=subprocess.PIPE, stderr=sys.stderr, bufsize=8388608)
            c.VVInstance = subprocess.Popen(\
                shlex.split("%s python %s --chkpnt_fn %s --sampleName %s --threads %d" %\
                            (taskSet, VVBin, chkpnt_fn, sampleName, numCpus) ),\
                            stdin=c.CTSInstance.stdout, stdout=subprocess.PIPE, stderr=sys.stderr, bufsize=8388608)
        except Exception as e:
            print >> sys.stderr, e
            sys.exit("Failed to start required processes. Exiting...")

        signal.signal(signal.SIGALRM, CheckRtCode)
        signal.alarm(2)

        def put(fh, inputs):
            for row in inputs:
                fh.write(row)
            fh.close()

        def get(fh, outputs):
            for row in fh:
                outputs.append(row)

        putThread = Thread(target = put, args = (c.GTInstance.stdin, inputs, ))
        getThread = Thread(target = get, args = (c.VVInstance.stdout, outputs, ))
        putThread.start()
        getThread.start()

        putThread.join()
        getThread.join()
        c.VVInstance.stdout.close()
        c.VVInstance.wait()
        c.CTSInstance.stdout.close()
        c.CTSInstance.wait()
        c.GTInstance.stdout.close()
        c.GTInstance.wait()
        signal.alarm(0)

    headers = []
    allOutputs = []
    allInputs = []
    inputs = []
    outputs = []
    previousCtg = ""
    flag = 1
    vcf_fh = subprocess.Popen(shlex.split("gzip -dcf %s" % (vcf_fn) ), stdout=subprocess.PIPE, bufsize=8388608)
    for row in vcf_fh.stdout:
        rowA = row.strip().split()
        if rowA[0][0] == "#":
            headers.append(row)
            continue
        if rowA[0] != previousCtg:
            if args.allChrom == False:
                if previousCtg not in chroms:
                    flag = 0
                else:
                    flag = 1
            if flag == 1 and len(inputs) != 0:
                print >> sys.stderr, "Working on chromosome: %s" % (previousCtg)
                RunOnACtg(previousCtg, inputs, outputs)
                for item in outputs:
                    allOutputs.append(item)
            outputs = []
            inputs = []
            previousCtg = rowA[0]
        inputs.append(row)
        allInputs.append(row)
    if args.allChrom == False:
        if previousCtg not in chroms:
            flag = 0
        else:
            flag = 1
    if flag == 1 and len(inputs) != 0:
        print >> sys.stderr, "Working on chromosome: %s" % (previousCtg)
        RunOnACtg(previousCtg, inputs, outputs)
        for item in outputs:
            allOutputs.append(item)
    # ---------------------------------------

    # --------------------------------------- Output Clairvoyante calls to VCF
    if args.outputVCF_fn != None:
        outputVCF_fh = open(args.outputVCF_fn, "w")
        for row in headers:
            outputVCF_fh.write(row)
        for row in allOutputs:
            outputVCF_fh.write(row)
    # ---------------------------------------

    # --------------------------------------- Result analysis section
    def ProcessVCFRecord(row):
        last = row[-1]
        p1, p2 = 0, 0
        if last.split(":")[0].find("/") != -1 or last.split(":")[0].find("|") != -1:
            varType = last.split(":")[0].replace("/","|").replace(".","0").split("|")
            p1, p2 = [int(x) for x in varType]
            p1, p2 = (p1, p2) if p1 < p2 else (p2, p1)
        else:
            varType = last.split(":")[0].replace(".","0")
            p1 = p2 = int(varType)
        multi = 0
        if p1 == 1 and p2 == 2:
            multi = 1
        return (multi, row[3], row[5], "\t".join([row[4], "/".join([str(p1), str(p2)])]))

    preChr = prePos = ""
    val_fh = open(val_fn, "w")
    iterAllOutputs = iter(allOutputs)
    iterAllInputs = iter(allInputs)
    inputA = next(iterAllInputs).strip().split()
    for output in iterAllOutputs:
        outputA = output.strip().split()
        while inputA[0] != outputA[0] or int(inputA[1]) < int(outputA[1]):
            multi, refAllele, _, pi = ProcessVCFRecord(inputA)
            if multi == 1:
                print >> val_fh, "B\t0\t%s\t%d\t%s\t%s" % (inputA[0], int(inputA[1]), refAllele, pi)
            else:
                print >> val_fh, "S\t0\t%s\t%d\t%s\t%s" % (inputA[0], int(inputA[1]),refAllele, pi)
            while True:
                try:
                    inputA = next(iterAllInputs).strip().split()
                except StopIteration:
                    break
                if inputA[0] != preChr or int(inputA[1]) != prePos:
                    preChr = inputA[0]; prePos = int(inputA[1])
                    break;
        if inputA[0] == outputA[0] and int(inputA[1]) == int(outputA[1]):
            multi, refAllele, _, pi = ProcessVCFRecord(inputA)
            _, _, qual, po = ProcessVCFRecord(outputA)
            if multi == 1:
                print >> val_fh, "B\t0\t%s\t%d\t%s\t%s" % (inputA[0], int(inputA[1]), refAllele, pi)
            elif pi == po:
                print >> val_fh, "M\t%s\t%s\t%d\t%s\t%s\t%s" % (qual, inputA[0], int(inputA[1]), refAllele, pi, po)
            else:
                print >> val_fh, "X\t%s\t%s\t%d\t%s\t%s\t%s" % (qual, inputA[0], int(inputA[1]), refAllele, pi, po)
            while True:
                try:
                    inputA = next(iterAllInputs).strip().split()
                except StopIteration:
                    break
                if inputA[0] != preChr or int(inputA[1]) != prePos:
                    preChr = inputA[0]; prePos = int(inputA[1])
                    break;
        elif inputA[0] == outputA[0] and int(inputA[1]) > int(outputA[1]):
            continue
        else:
            print >> sys.stderr, "Should not reach here:\n%s\n%s" % (inputA, outputA)
            sys.exit(-1)
    # ---------------------------------------


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
            description="Skyhawk: An Artificial Neural Network-based discriminator for validating clinically significant genomic variants" )

    parser.add_argument('--chkpnt_fn', type=str, default = None,
            help="Input a Clairvoyante model")

    parser.add_argument('--ref_fn', type=str, default="ref.fa",
            help="Reference fasta input, default: %(default)s")

    parser.add_argument('--bam_fn', type=str, default="bam.bam",
            help="BAM input, default: %(default)s")

    parser.add_argument('--vcf_fn', type=str, default=None,
            help="Sites for validation, sorted VCF input, default: %(default)s")

    parser.add_argument('--val_fn', type=str, default = None,
            help="Output validation results")

    parser.add_argument('--outputVCF_fn', type=str, default = None,
            help="Output Clairvoyante variant calls into a VCF file")

    parser.add_argument('--allChrom', type=param.str2bool, nargs='?', const=False, default=False,
            help="Work on all chromosomes, default only on chr{1..22,X,Y} and {1..22,X,Y}")

    parser.add_argument('--sampleName', type=str, default = "SAMPLE",
            help="Define the sample name to be shown in the VCF file")

    parser.add_argument('--threads', type=int, default = None,
            help="Number of threads, optional")

    parser.add_argument('--dcov', type=int, default=8000,
            help="Cap depth per position at %(default)s")

    parser.add_argument('--samtools', type=str, default="samtools",
            help="Path to the 'samtools', default: %(default)s")

    parser.add_argument('--pypy', type=str, default="pypy",
            help="Path to the 'pypy', default: %(default)s")

    args = parser.parse_args()

    if len(sys.argv[1:]) == 0:
        parser.print_help()
        sys.exit(1)

    Run(args)

