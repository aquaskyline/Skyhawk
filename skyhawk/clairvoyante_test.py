import sys
import os
import time
import argparse
import param
import logging
import numpy as np
from threading import Thread
from math import log

logging.basicConfig(format='%(message)s', level=logging.INFO)
num2base = dict(zip((0, 1, 2, 3), "ACGT"))
v1Type2Name = dict(zip((0, 1, 2, 3, 4), ('HET', 'HOM', 'INS', 'DEL', 'REF')))
v2Zygosity2Name = dict(zip((0, 1), ('HET', 'HOM')))
v2Type2Name = dict(zip((0, 1, 2, 3), ('REF', 'SNP', 'INS', 'DEL')))
v2Length2Name = dict(zip((0, 1, 2, 3, 4, 5), ('0', '1', '2', '3', '4', '4+')))
maxVarLength = 5
inferIndelLengthMinimumAF = 0.125

def Run(args):
    # create a Clairvoyante
    import utils_v2 as utils
    import clairvoyante_v3 as cv
    utils.SetupEnv()
    if args.threads == None:
        if args.tensor_fn == "PIPE":
            param.NUM_THREADS = 1
    else:
        param.NUM_THREADS = args.threads
    m = cv.Clairvoyante()
    m.init()

    m.restoreParameters(os.path.abspath(args.chkpnt_fn))
    Test(args, m, utils)


def Output(args, call_fh, num, XBatch, posBatch, base, z, t, l):
    if num != len(base):
      sys.exit("Inconsistent shape between input tensor and output predictions %d/%d" % (num, len(base)))

    #          --------------  ------  ------------    ------------------
    #          Base chng       Zygo.   Var type        Var length
    #          A   C   G   T   HET HOM REF SNP INS DEL 0   1   2   3   4   >=4
    #          0   1   2   3   4   5   6   7   8   9   10  11  12  13  14  15
    for j in range(len(base)):
        # Get variant type, 0:REF, 1:SNP, 2:INS, 3:DEL
        varType = np.argmax(t[j])
        # Get zygosity, 0:HET, 1:HOM
        varZygosity = np.argmax(z[j])
        # Get Indel Length, 0:0, 1:1, 2:2, 3:3, 4:4, 5:>4
        varLength = np.argmax(l[j])
        # Get chromosome, coordination and reference bases with flanking param.flankingBaseNum flanking bases at coordination
        chromosome, coordination, refSeq = posBatch[j].split(":")
        # Get genotype quality
        sortVarType = np.sort(t[j])[::-1]
        sortZygosity = np.sort(z[j])[::-1]
        sortLength = np.sort(l[j])[::-1]
        qual = int(-4.343 * log((sortVarType[1]*sortZygosity[1]*sortLength[1]  + 1e-300) / (sortVarType[0]*sortZygosity[0]*sortLength[0]  + 1e-300)))
        #if qual > 999: qual = 999
        # Get possible alternative bases
        sortBase = base[j].argsort()[::-1]
        base1 = num2base[sortBase[0]]
        base2 = num2base[sortBase[1]]
        # Initialize other variables
        refBase = ""; altBase = ""; inferredIndelLength = 0; dp = 0; info = [];
        # For SNP
        if varType == 1 or varType == 0: # SNP or REF
            coordination = int(coordination)
            refBase = refSeq[param.flankingBaseNum]
            if varType == 1: # SNP
                altBase = base1 if base1 != refBase else base2
                #altBase = "%s,%s" % (base1, base2)
            elif varType == 0: # REF
                altBase = refBase
            dp = sum(XBatch[j,param.flankingBaseNum,:,0] + XBatch[j,param.flankingBaseNum,:,3])
        elif varType == 2: # INS
            # infer the insertion length
            if varLength == 0: varLength = 1
            dp = sum(XBatch[j,param.flankingBaseNum+1,:,0] + XBatch[j,param.flankingBaseNum+1,:,1])
            if varLength != maxVarLength:
                for k in range(param.flankingBaseNum+1, param.flankingBaseNum+varLength+1):
                    altBase += num2base[np.argmax(XBatch[j,k,:,1])]
            else:
                for k in range(param.flankingBaseNum+1, 2*param.flankingBaseNum+1):
                    referenceTensor = XBatch[j,k,:,0]; insertionTensor = XBatch[j,k,:,1]
                    if k < (param.flankingBaseNum + maxVarLength) or sum(insertionTensor) >= (inferIndelLengthMinimumAF * sum(referenceTensor)):
                        inferredIndelLength += 1
                        altBase += num2base[np.argmax(insertionTensor)]
                    else:
                        break
            coordination = int(coordination)
            refBase = refSeq[param.flankingBaseNum]
            # insertions longer than (param.flankingBaseNum-1) are marked SV
            if inferredIndelLength >= param.flankingBaseNum:
                altBase = "<INS>"
                info.append("SVTYPE=INS")
            else:
                altBase = refBase + altBase
        elif varType == 3: # DEL
            if varLength == 0: varLength = 1
            dp = sum(XBatch[j,param.flankingBaseNum+1,:,0] + XBatch[j,param.flankingBaseNum+1,:,2])
            # infer the deletion length
            if varLength == maxVarLength:
                for k in range(param.flankingBaseNum+1, 2*param.flankingBaseNum+1):
                    if k < (param.flankingBaseNum + maxVarLength) or sum(XBatch[j,k,:,2]) >= (inferIndelLengthMinimumAF * sum(XBatch[j,k,:,0])):
                        inferredIndelLength += 1
                    else:
                        break
            # deletions longer than (param.flankingBaseNum-1) are marked SV
            coordination = int(coordination)
            if inferredIndelLength >= param.flankingBaseNum:
                refBase = refSeq[param.flankingBaseNum]
                altBase = "<DEL>"
                info.append("SVTYPE=DEL")
            elif varLength != maxVarLength:
                refBase = refSeq[param.flankingBaseNum:param.flankingBaseNum+varLength+1]
                altBase = refSeq[param.flankingBaseNum]
            else:
                refBase = refSeq[param.flankingBaseNum:param.flankingBaseNum+inferredIndelLength+1]
                altBase = refSeq[param.flankingBaseNum]
        if inferredIndelLength > 0 and inferredIndelLength < param.flankingBaseNum: info.append("LENGUESS=%d" % inferredIndelLength)
        infoStr = ""
        if len(info) == 0: infoStr = "."
        else: infoStr = ";".join(info)
        gtStr = ""
        if varType == 0: gtStr = "0/0"
        elif varZygosity == 0: gtStr = "0/1"
        elif varZygosity == 1: gtStr = "1/1"

        print >> call_fh, "%s\t%d\t.\t%s\t%s\t%d\t.\t%s\tGT:GQ:DP\t%s:%d:%d" % (chromosome, coordination, refBase, altBase, qual, infoStr, gtStr, qual, dp)


def Test(args, m, utils):
    if args.call_fn != "PIPE":
        call_fh = open(args.call_fn, "w")
    else:
        call_fh = sys.stdout
    tensorGenerator = utils.GetTensor( args.tensor_fn, param.predictBatchSize )
    #logging.info("Validating variants ...")
    predictStart = time.time()
    end = 0; end2 = 0; terminate = 0
    end2, num2, XBatch2, posBatch2 = next(tensorGenerator)
    m.predictNoRT(XBatch2)
    base = m.predictBaseRTVal; z = m.predictZygosityRTVal; t = m.predictVarTypeRTVal; l = m.predictIndelLengthRTVal
    if end2 == 0:
        end = end2; num = num2; XBatch = XBatch2; posBatch = posBatch2
        end2, num2, XBatch2, posBatch2 = next(tensorGenerator)
        while True:
            if end == 1:
                terminate = 1
            threadPool = []
            if end == 0:
                threadPool.append(Thread(target=m.predictNoRT, args=(XBatch2, )))
            threadPool.append(Thread(target=Output, args=(args, call_fh, num, XBatch, posBatch, base, z, t, l, )))
            for t in threadPool: t.start()
            if end2 == 0:
                end3, num3, XBatch3, posBatch3 = next(tensorGenerator)
            for t in threadPool: t.join()
            base = m.predictBaseRTVal; z = m.predictZygosityRTVal; t = m.predictVarTypeRTVal; l = m.predictIndelLengthRTVal
            if end == 0:
                end = end2; num = num2; XBatch = XBatch2; posBatch = posBatch2
            if end2 == 0:
                end2 = end3; num2 = num3; XBatch2 = XBatch3; posBatch2 = posBatch3
            #print >> sys.stderr, end, end2, end3, terminate
            if terminate == 1:
                break
    elif end2 == 1:
        Output(args, call_fh, num2, XBatch2, posBatch2, base, z, t, l)

    #logging.info("Total time elapsed: %.2f s" % (time.time() - predictStart))


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
            description="Skyhawk validation core" )

    parser.add_argument('--tensor_fn', type=str, default = "PIPE",
            help="Input tensors, use PIPE for standard input")

    parser.add_argument('--chkpnt_fn', type=str, default = None,
            help="Input a Clairvoyante model")

    parser.add_argument('--call_fn', type=str, default = "PIPE",
            help="Output validation results")

    parser.add_argument('--sampleName', type=str, default = "SAMPLE",
            help="Define the sample name to be shown in the VCF file")

    parser.add_argument('--threads', type=int, default = None,
            help="Number of threads, optional")

    args = parser.parse_args()

    if len(sys.argv[1:]) == 0:
        parser.print_help()
        sys.exit(1)

    Run(args)

