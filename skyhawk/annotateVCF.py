import os
import sys
import gzip
import argparse

def CheckFileExist(fn):
    if not os.path.isfile(fn):
        return None
    return os.path.abspath(fn)


def AnnotateVCF( args ):
    vcf_fn = args.vcf_fn
    skyhawk_fn = args.skyhawk_fn
    annovcf_fn = args.annovcf_fn

    if vcf_fn == None or CheckFileExist(vcf_fn) == None:
        print >> sys.stderr, "Missing VCF input"; sys.exit(1)
    if skyhawk_fn == None or CheckFileExist(skyhawk_fn) == None:
        print >> sys.stderr, "Missing Skyhawk input"; sys.exit(1)
    if annovcf_fn == None:
        print >> sys.stderr, "Missing VCF output filename"; sys.exit(1)

    results = {}

    with gzip.open(skyhawk_fn, "rb") if skyhawk_fn.endswith(".gz") else open(skyhawk_fn, "r") as f:
        for row in f:
            col = row.split()
            results[col[2] + "-" + col[3]] = row[0]

    with gzip.open(vcf_fn, "rb") if vcf_fn.endswith(".gz") else open(vcf_fn, "r") as f, open(annovcf_fn, "w") as o:
        for row in f:
            row = row.rstrip("\n")
            col = row.split()
            if col[0] == "#CHROM":
                print >> o, '##FILTER=<ID=SKYHAWK,Description="Skyhawk filtered">'
                print >> o, row
            elif col[0][0] == col[0][1] and col[0][0] == "#":
                print >> o, row
            else:
                stat = results[col[0] + "-" + col[1]]
                if stat == "X" or stat == "S":
                    col[6] = "SKYHAWK"
                else:
                    col[6] = "PASS"
                print >> o, "\t".join(col)


def main():
    parser = argparse.ArgumentParser(
            description="Annotate an VCF according the Skyhawk output" )

    parser.add_argument('--vcf_fn', type=str, default=None,
            help="Unannotated VCF file input, mandatory")

    parser.add_argument('--skyhawk_fn', type=str, default=None,
            help="Skyhawk decision input, mandatory")

    parser.add_argument('--annovcf_fn', type=str, default=None,
            help="Annotated VCF file output, mandatory")

    args = parser.parse_args()

    if len(sys.argv[1:]) == 0:
        parser.print_help()
        sys.exit(1)

    AnnotateVCF( args )


if __name__ == "__main__":
    main()
