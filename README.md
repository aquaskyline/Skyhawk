# Skyhawk: An Artificial Neural Network-based discriminator for validating clinically significant genomic variants
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)  
Contact: Ruibang Luo  
Email: rbluo@cs.hku.hk  

***

## Installation
```shell
git clone https://github.com/aquaskyline/Skyhawk.git
cd Skyhawk
curl http://www.bio8.cs.hku.hk/skyhawkModels.tbz | tar -jxf -
```

## Quick Start after Installation
```shell
cd skyhawk/testingData
python ../skyhawk/validateVar.py \
       --chkpnt_fn ../trainedModels/illumina-novoalign-2500-tspcrfree-hg001+hg002+hg003+hg004+hg005-hg38/learningRate1e-3.epoch100.learningRate1e-4.epoch200 \
       --ref_fn chr21.fa.gz \
       --bam_fn chr21:14069696-14269696.bam \
       --vcf_fn chr21:14069696-14269696.vcf.gz \
       --val_fn validation.out
less validation.out
```

***

## Introduction
With the increasing throughput and reliability of sequencing technologies in the recent years, it is getting common that medical doctors rely on sequencing to make better diagnostics for cancers and rare diseases. Among the interpretable results that sequencing can provide, genetic variants that have been reported in renowned databases such as Clinvar and HGMD, with evidence showing that they associate with certain symptoms and therapies, are considered as actionable genetic variant candidates. However, even though the state-of-the-art variant callers achieve better precision and sensitivity, it is still not uncommon for the variant callers to produce false positive variants with somehow a pretty high probability, which makes them unable to tell apart from the true positives. The situation gets even worse when the callers are set to favor sensitivity over precision, which is often the case in clinical practices. The false positives variants, if not being sanitized, will lead to a spurious clinical diagnosis. Instead of relying only on what a variant caller tells, clinical doctors usually verify the correctness of actionable genetic variants by eyes, with the help of `IGV` or `SAMtools tview`. 'Skyhawk' was designed to expedite the process and save the doctors from eye checking the variant, using a deep neural network based "eye", trained with millions of samples on how a true variant "looks like" in different settings.  

***

## Prerequisition
### Basics
Skyhawk requires Python 2.7.  
Make sure you have Tensorflow ≥ 1.0.0 installed, the following commands install the lastest CPU version of Tensorflow:  

```shell
pip install tensorflow  
pip install blosc  
pip install intervaltree  
pip install numpy  
```

To check the version of Tensorflow you have installed:  

```shell
python -c 'import tensorflow as tf; print(tf.__version__)'
```

Skyhawk runs on CPU. Although Skyhawk can benefit from using GPU, the speed up is insignificant. This is because the feed-forward network computation is light compare with other tasks including parsing reads from a BAM file and formatting the results into a VCF file. We suggest disabling GPU temperarily on a GPU-enabled system when running Skyhawk with command `export CUDA_VISIBLE_DEVICES="-1"`.  

### Speed up with PyPy
Without a change to the code, using PyPy python interpreter on Skyhawk modules including `dataPrepScripts/ExtractVariantCandidates.py` and `dataPrepScripts/CreateTensorSites.py` gives a 5-10 times speed up. Pypy python interpreter can be installed by apt-get, yum, Homebrew, MacPorts, etc. If you have no root access to your system, the official website of Pypy provides a portable binary distribution for Linux. Following is a rundown extracted from Pypy's website (pypy-5.8 in this case, you might be working on a newer version) on how to install the binaries.  

```shell
wget https://bitbucket.org/squeaky/portable-pypy/downloads/pypy-5.8-1-linux_x86_64-portable.tar.bz2
tar -jxf pypy-5.8-1-linux_x86_64-portable.tar.bz2
cd pypy-5.8-linux_x86_64-portable/bin
./pypy -m ensurepip
./pip install -U pip wheel intervaltree blosc
# Use pypy as an inplace substitution of python to run the scripts in dataPrepScripts/
```

If you can use apt-get or yum in your system, please install both `pypy` and `pypy-dev` packages. And then install the pip for pypy.  

```shell
sudo apt-get install pypy pypy-dev
wget https://bootstrap.pypa.io/get-pip.py
sudo pypy get-pip.py
sudo pypy -m pip install blosc
sudo pypy -m pip install intervaltree
```

Skywawk will fallback to using python if pypy intepreter doesn't exist. It's OK to run Skyhawk without pypy, albeit it runs a few times slower (13 minutes vs. 3 minutes on 50k variants).  

*Pypy is an awesome Python JIT intepreter, you can donate to [the project](https://pypy.org).*  

***

## Quick Start
### Download testing dataset

```shell
wget 'http://www.bio8.cs.hku.hk/testingData.tar'
tar -xf testingData.tar
```

### Validate variants

```shell
python ./skyhawk/validateVar.py \
       --chkpnt_fn ./trainedModels/illumina-novoalign-2500-tspcrfree-hg001+hg002+hg003+hg004+hg005-hg38/learningRate1e-3.epoch100.learningRate1e-4.epoch200 \
       --ref_fn ../testingData/chr21/chr21.fa \
       --bam_fn ../testingData/chr21/chr21.bam \
       --vcf_fn ../testingData/chr21/chr21.vcf \
       --thread 4 \
       --val_fn validationOutput.txt
less -S validationOutput.txt
```
### Speed up by running multiple chromosomes in parallel

Skyhawk usually takes less than a minute to validate ten thousand variants. In clinical context, especially when using Whole Exome Sequencing, the number variants to be validated would seldom exceed ten thousand. But if you use Skyhawk on million of variants for general variant filtering, you will need to split the run into chromosomes and run them in parallel.  

```shell
# Index the input VCF for random retrival
bgzip input.vcf
tabix -fp vcf input.vcf.gz
# Split the input VCF into chromosomes, please use appropriate chromosome names (w/ or w/o the "chr" prefix)
for i in {1..22} X Y; do tabix -pvcf input.vcf.gz chr$i > chr$i.vcf; done
# Run validateVar.py in parallel
for i in {1..22} X Y; do \
python ./skyhawk/validateVar.py \
       --chkpnt_fn ./trainedModels/illumina-novoalign-2500-tspcrfree-hg001+hg002+hg003+hg004+hg005-hg38/learningRate1e-3.epoch100.learningRate1e-4.epoch200 \
       --ref_fn ../hg38.fa \
       --bam_fn ../aln.bam \
       --vcf_fn chr$i.vcf \
       --thread 4 \
       --val_fn chr$i.out.txt &\true;
done
```

This will speed up Skyhawk to less than an hour for 3.5 million variants. 

***

## Build a Model

Please refer to the [Clairvoyante](https://github.com/aquaskyline/Clairvoyante) project.  

***

## Understand the output

There are nine columns in the output:  

1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
--- | --- | --- | --- | --- | --- | --- | --- | --- |
Validation result | Skyhawk Quality | Chromosome | Position | Reference Allele | Input Alternative Allele | Input Genotype | Skyhawk Alternative Allele | Skyhawk Genotype

* There are four types of validation result:
 * M: Validated variant
 * X: Suspecious and unvalidated variant, manual review required
 * B: Variant with multiple alternative allele, manual review required
 * S: No read cover in the input BAM

***

## Folder Stucture and Program Descriptions
*Run the program to get the parameter details.*  

`dataPrepScripts/` | Data Preparation Scripts. Outputs are gzipped unless using standard output. Scripts in this folder are compatible with `pypy`.
--- | ---
`GetTruth.py`| Extract the variant positions and details from a truth VCF. Input: VCF.
`CreateTensorSites.py`| Create tensorflow tensors for variants.

`skyhawk/` | Script for variant validation. Scripts in this folder are NOT compatible with `pypy`. Please run with `python`.
--- | ---
`validateVar.py` | Main program for validating variants.
`clairvoyante_test.py `| Code to utilize the [Clairvoyante](https://github.com/aquaskyline/Clairvoyante) artificial neural network. 

***

## About the Trained Models
The trained models are in the `trainedModels/` folder.  


Folder | Tech | LibPrep | Aligner | Ref | Sample |
--- |:---:|:---:|:---:|:---:| :---: |
`illumina-novoalign-2500-tspcrfree-`<br>`hg001+hg002+hg003+hg004+hg005-hg38` | Illumina HiSeq2500 | TruSeq PCR-free | Nonoalign 3.02.07 | hg38 | NA12878+NA24385+NA24149<br>+NA24143+NA24631 |
`illumina-novoalign-2500-tspcrfree-`<br>`hg001+hg002+hg003+hg004+hg005-hg19` | Illumina HiSeq2500 | TruSeq PCR-free | Nonoalign 3.02.07 | hg19 | NA12878+NA24385+NA24149<br>+NA24143+NA24631 |
`illumina-novoalign-2500-tspcrfree-`<br>`hg001+hg002+hg003+hg004-hg38` | Illumina HiSeq2500 | TruSeq PCR-free | Nonoalign 3.02.07 | hg38 | NA12878+NA24385+NA24149<br>+NA24143 |
`illumina-novoalign-2500-tspcrfree-`<br>`hg001+hg002-hg38` | Illumina HiSeq2500 | TruSeq PCR-free | Nonoalign 3.02.07 | hg38 | NA12878+NA24385 |
`illumina-novoalign-2500-tspcrfree-`<br>`hg001-hg38` | Illumina HiSeq2500 | TruSeq PCR-free | Nonoalign 3.02.07 | hg38 | NA12878 |
`illumina-novoalign-2500-tspcrfree-`<br>`hg002-hg38` | Illumina HiSeq2500 | TruSeq PCR-free | Nonoalign 3.02.07 | hg38 | NA24385 |
`illumina-isaac-2000-tspcrfree-`<br>`hg001-hg19` | Illumina HiSeq2000 | TruSeq PCR-free | Isaac | hg19 | NA12878 |
`illumina-isaac-4000-tsnano550-`<br>`hg001-hg19` | Illumina HiSeq4000 | TruSeq Nano 550 | Isaac | hg19 | NA12878 |
`illumina-isaac-x-tsnano2.5-`<br>`hg001-hg19` | Illumina HiSeq X | TruSeq Nano 2.5 | Isaac | hg19 | NA12878 |
`illumina-isaac-ns500-tsnano350-`<br>`hg001-hg19` | Illumina NextSeq 500 | TruSeq Nano 350 | Isaac | hg19 | NA12878 |
`illumina-isaac-s1xp-tsnano350-`<br>`hg001-hg38` | Illumina NovaSeq S1xp | TruSeq Nano 350 | Isaac | hg38 | NA12878 |
`illumina-isaac-s2-nextraflex-`<br>`hg001-hg38` | Illumina NovaSeq S2 | TruSeq Nextera Flex | Isaac | hg38 | NA12878 |
`illumina-isaac-s4-nextraflex-`<br>`hg001-hg38` | Illumina NovoSeq S4 | TruSeq Nextera Flex | Isaac | hg38 | NA12878 |

<sup>\*</sup> Each folder contains one or more models. Each model contains three files suffixed `data-00000-of-00001`, `index` and `meta`, respectively. Only the prefix is needed when using the model with Clairvoyante. Using the prefix `learningRate1e-3.epoch999.learningRate1e-4.epoch1499` as an example, it means that the model has trained for 1000 epochs at learning rate 1e<sup>-3</sup>, then another 500 epochs at learning rate 1e<sup>-4</sup>. Lambda for L2 regularization was set the same as learning rate.  

* Experiments in issue (#4) show that using the Novoalign models for BWA alignments will increase the accuracy of Skyhawk.  

***

## About the Testing Data
The testing dataset 'testingData.tar' includes:  
1) the Illumina alignments of chr21 and chr22 on GRCh38 from [GIAB Github](ftp://ftp-trace.ncbi.nlm.nih.gov/giab/ftp/data/NA12878/NIST_NA12878_HG001_HiSeq_300x/NHGRI_Illumina300X_novoalign_bams/HG001.GRCh38_full_plus_hs38d1_analysis_set_minus_alts.300x.bam), downsampled to 50x.  
2) the truth variants v3.3.2 from [GIAB](ftp://ftp-trace.ncbi.nlm.nih.gov/giab/ftp/release/NA12878_HG001/NISTv3.3.2/GRCh38).  

***

## Limitations
### On variants with two alternative alleles (GT: 1/2)
Skyhawk doesn't support validating variants with more than one alternative allele. Skyhawk will mark the variants with multiple alleles as type 'B' in the results, suggesting these variants were not validated by Skyhawk and require manual validation. Although we will further extend the Skyhawk to support genome variants with multiple alternative alleles, as there are just few number of them and they are more error-prone, we suggest we always review these variants manually.  
