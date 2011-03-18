#!/usr/bin/env python
# encoding: utf-8
"""
merge_cuff_asms.py

Created by Cole Trapnell on 2011-03-17.
Copyright (c) 2011 Cole Trapnell. All rights reserved.
"""

import sys
import getopt
from datetime import datetime, date, time
import shutil
import subprocess
import errno
import os
import tempfile
import warnings

help_message = '''
merge_cuff_asms takes two or more Cufflinks GTF files and merges them into a 
single unified transcript catalog.  Optionally, you can provide the script 
with a reference GTF, and the script will use it to attach gene names and other
metadata to the merged catalog.

usage:
    merge_cuff_asms [-r reference.gtf] <cuff_asm_1.gtf> ... <cuff_asm_N.gtf>
'''

output_dir = "./"
logging_dir = output_dir + "logs/"
run_log = None
run_cmd = None
tmp_dir = output_dir + "tmp/"
bin_dir = sys.path[0] + "/"
run_meta_assembly = True


class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

class TestParams:

    class SystemParams:
        def __init__(self,
                     threads,
                     keep_tmp):
            self.threads = threads
            self.keep_tmp = keep_tmp

        def parse_options(self, opts):
            for option, value in opts:
                if option in ("-p", "--num-threads"):
                    self.threads = int(value)
                if option in ("--keep-tmp"):
                    self.keep_tmp = True

        def check(self):
            pass

    def __init__(self):
        self.system_params = self.SystemParams(1,               # threads
                                               False)           # keep_tmp
        self.ref_gtf = None
        self.fasta = None
        self.out_prefix=""

    def check(self):
        self.system_params.check()

    def parse_options(self, argv):
        try:
            opts, args = getopt.getopt(argv[1:],
                                       "hvp:o:G:M:s:q:",
                                       ["version",
                                        "help",
                                        "ref-sequence=",
                                        "ref-gtf=",
                                        "output-dir=",
                                        "num-threads=",
                                        "out-prefix=",
                                        "keep-tmp"])
        except getopt.error, msg:
            raise Usage(msg)

        self.system_params.parse_options(opts)

        global output_dir
        global logging_dir
        global tmp_dir

        # option processing
        for option, value in opts:
            if option in ("-v", "--version"):
                print "merge_cuff_asms v%s" % (get_version())
                exit(0)
            if option in ("-h", "--help"):
                raise Usage(use_message)
            if option in ("-G", "--ref-gtf"):
                self.ref_gtf = value
            if option in ("-s", "--ref-sequence"):
                self.fasta = value
            if option == "--out-prefix":
                self.out_prefix = value
            if option in ("-o", "--output-dir"):
                output_dir = value + "/"
                logging_dir = output_dir + "logs/"
                tmp_dir = output_dir + "tmp/"

        return args


def right_now():
    curr_time = datetime.now()
    return curr_time.strftime("%c")

def prepare_output_dir():

    print >> sys.stderr, "[%s] Preparing output location %s" % (right_now(), output_dir)
    if os.path.exists(output_dir):
        pass
    else:
        os.mkdir(output_dir)

    if os.path.exists(logging_dir):
        pass
    else:
        os.mkdir(logging_dir)

    if os.path.exists(tmp_dir):
        pass
    else:
        os.mkdir(tmp_dir)

def formatTD(td):
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    seconds = td.seconds % 60
    return '%02d:%02d:%02d' % (hours, minutes, seconds)

def tmp_name(prefix):
    tmp_root = output_dir + "tmp/"
    if os.path.exists(tmp_root):
        pass
    else:
        os.mkdir(tmp_root)
    return tmp_root + prefix + os.tmpnam().split('/')[-1]

def cufflinks(params,
              out_dir,
              sam_file,
              gtf_file=None,
              extra_opts=["-q", "--overhang-tolerance", "200", "--library-type=transfrags",  "-A","0.0", "-F", "0.0", "-j 0.0"],
              lsf=False,
              curr_queue=None):
    if gtf_file != None:
        print >> sys.stderr, "[%s] Quantitating transcripts" % (right_now())
    else:
        print >> sys.stderr, "[%s] Assembling transcripts" % (right_now())

    cmd = ["cufflinks"]

    if out_dir != None and out_dir != "":
        cmd.extend(["-o", out_dir])

    if gtf_file != None:
        cmd.extend(["-G", gtf_file])

    if extra_opts != None:
        cmd.extend(extra_opts)

    # Run Cufflinks with more than one thread?
    cmd.extend(["-p", str(params.system_params.threads)])

    cmd.append(sam_file)

    try:
        print >> run_log, " ".join(cmd)
        ret = subprocess.call(cmd)
        if ret != 0:
            print >> sys.stderr, fail_str, "Error: could not execute cufflinks"
            exit(1)
    # cufflinks not found
    except OSError, o:
        if o.errno == errno.ENOTDIR or o.errno == errno.ENOENT:
            print >> sys.stderr, fail_str, "Error: cufflinks not found on this system.  Did you forget to include it in your PATH?"
        exit(1)

def cuffcompare(params, prefix, ref_gtf, fasta, cuff_gtf):

    print >> sys.stderr, "[%s] Comparing reference %s to assembly %s" % (right_now(), ref_gtf, cuff_gtf)
    cmd = ["cuffcompare"]

    if  prefix != None:
        cmd.extend(["-o", prefix])
    if  ref_gtf != None:
        cmd.extend(["-r", ref_gtf])
    if  fasta != None:
        cmd.extend(["-s", fasta])
    if type(cuff_gtf) == ListType:
        for g in cuff_gtf:
            cmd.extend([g])
    else:
        cmd.extend([cuff_gtf])

    try:
        print >> run_log, " ".join(cmd)
        ret = subprocess.call(cmd)
        if ret != 0:
            print >> sys.stderr, fail_str, "Error: could not execute cuffcompare"
            exit(1)
    # cuffcompare not found
    except OSError, o:
        if o.errno == errno.ENOTDIR or o.errno == errno.ENOENT:
            print >> sys.stderr, fail_str, "Error: cuffcompare not found on this system.  Did you forget to include it in your PATH?"
        exit(1)

def gtf_to_sam(gtf_filename):

    sam_out = tmp_name("gtf2sam_")

    cmd = ["gtf_to_sam"]
    cmd.append(gtf_filename)
    cmd.append(sam_out)
    try:
        print >> run_log, " ".join(cmd)
        ret = subprocess.call(cmd)
        if ret != 0:
            print >> sys.stderr, fail_str, "Error: could not execute gtf_to_sam"
            exit(1)
    # gtf_to_sam not found
    except OSError, o:
        if o.errno == errno.ENOTDIR or o.errno == errno.ENOENT:
            print >> sys.stderr, fail_str, "Error: gtf_to_sam not found on this system.  Did you forget to include it in your PATH?"
        exit(1)
    return sam_out

def test_input_files(filename_list):
    """This function takes a file that contains a list of GTF files,
       tests accessibility of each, and returns the list of filenames"""

    OK = True
    input_files = []
    for line in filename_list:
        line = line.strip()

        # Skip comment line
        if len(line) == 0 or line[0] == "#":
            continue
        try:
            g = open(line,"r")
            input_files.append(line)

        except OSError, o:
            if o.errno == errno.ENOTDIR or o.errno == errno.ENOENT:
                print >> sys.stderr, fail_str, "Error: could not open %s" % line
            OK = False
    if OK == False:
        sys.exit(1)
    return input_files

def convert_gtf_to_sam(gtf_filename_list):
    """This function takes a list of GTF files, converts them all to
       temporary SAM files, and returns the list of temporary file names."""
    print >> sys.stderr, "[%s] Converting GTF files to SAM" % (right_now())
    OK = True
    sam_input_filenames = []
    for line in gtf_filename_list:
        try:
            sam_out = gtf_to_sam(line)
            sam_input_filenames.append(sam_out)
        except OSError, o:
            if o.errno == errno.ENOTDIR or o.errno == errno.ENOENT:
                print >> sys.stderr, fail_str, "Error: could not open %s" % line
            OK = False
    if OK == False:
        sys.exit(1)
    return sam_input_filenames

def merge_sam_inputs(sam_input_list):
    sorted_map_name = tmp_name( "mergeSam_")

    sorted_map = open(sorted_map_name, "w")

    sort_cmd =["sort",
               "-k",
               "3,3",
               "-k",
               "4,4n",
               "--temporary-directory="+tmp_dir]
    sort_cmd.extend(sam_input_list)

    print >> run_log, " ".join(sort_cmd), ">", sorted_map_name
    subprocess.call(sort_cmd,
                   stdout=open(sorted_map_name, "w"))
    return sorted_map_name

def compare_to_reference(meta_asm_gtf, ref_gtf, fasta):
    print >> sys.stderr, "[%s] Comparing against reference file %s" % (right_now(), ref_gtf)
    if fasta != None:
        comp_cmd = '''cuffcompare -o meta_asm_vs_GENCODE -r %s -s %s %s %s;''' % (ref_gtf, fasta, meta_asm_gtf, meta_asm_gtf)
    else:
        comp_cmd = '''cuffcompare -o meta_asm_vs_GENCODE -r %s %s %s;''' % (ref_gtf, meta_asm_gtf, meta_asm_gtf)

    #cmd = bsub_cmd(comp_cmd, "/gencode_cmp", True, job_mem=8)
    cmd = comp_cmd

    try:
        print >> run_log, cmd
        ret = subprocess.call(cmd,shell=True)
        if ret != 0:
            print >> sys.stderr, fail_str, "Error: could not execute cuffcompare"
            exit(1)
        tmap_out = meta_asm_gtf.split("/")[-1] + ".tmap"
        shutil.copy2(tmap_out, "./meta_asm_vs_GENCODE.tmap")
        return ("./meta_asm_vs_GENCODE.combined.gtf", tmap_out)
    # cuffcompare not found
    except OSError, o:
        if o.errno == errno.ENOTDIR or o.errno == errno.ENOENT:
            print >> sys.stderr, fail_str, "Error: cuffcompare not found on this system.  Did you forget to include it in your PATH?"
        exit(1)
        
def select_gtf(gtf_in_filename, ids, gtf_out_filename):
    f_gtf = open(gtf_in_filename)
    #print >> sys.stderr, "Select GTF: Ids are: "
    #print >> sys.stderr, ids
    #print >> sys.stderr, "reference gtf file name:"
    #print >> sys.stderr, gtf_in_filename
    out_gtf = open(gtf_out_filename, "w")
    for line in f_gtf:
        line = line.strip()
        cols = line.split('\t')
        if len(cols) < 9:
            continue
        attrs = cols[8]
        attr_cols = attrs.split(';')
        for col in attr_cols:
            if col.find("transcript_id") != -1:
                first_quote = col.find('"')
                last_quote = col.find('"', first_quote + 1)
                transcript = col[first_quote + 1:last_quote]
                #print >> sys.stderr, transcript
                if transcript in ids:
                    print >> out_gtf, line


def merge_gtfs(gtf_filenames, merged_gtf, ref_gtf=None):
    print >> sys.stderr, "[%s] Merging linc gtf files with cuffcompare" % (right_now())
    cmd = ["cuffcompare"]

    cmd.extend(["-o", merged_gtf])
    if ref_gtf != None:
        cmd.extend(["-r", ref_gtf])

    cmd.extend(gtf_filenames)
    cmd = " ".join(cmd)
    #cmd = bsub_cmd(cmd, "/merge_gtf", True, job_mem=8)

    try:
        print >> run_log, cmd
        ret = subprocess.call(cmd, shell=True)
        if ret != 0:
            print >> sys.stderr, fail_str, "Error: could not execute cuffcompare"
            exit(1)
        return merged_gtf + ".combined.gtf"
    # cuffcompare not found
    except OSError, o:
        if o.errno == errno.ENOTDIR or o.errno == errno.ENOENT:
            print >> sys.stderr, fail_str, "Error: cuffcompare not found on this system.  Did you forget to include it in your PATH?"
        exit(1)

def cuffcompare_all_assemblies(gtf_input_files):
    print >> sys.stderr, "Cuffcmpare all assemblies GTFs"
    cmd = ["cuffcompare"]
    gtf_lst=" ".join(gtf_input_files)
    cuffcompare(None, "cuffcmpr1" , None,None, gtf_input_files)
    print >> sys.stderr, "Cuffcmpare all assemblies GTFs : run second cuffcompare"
    cuffcompare(None, "cuffcmpr2" , "cuffcmpr1.combined.gtf",None, "cuffcmpr1.combined.gtf")
    tmap="cuffcmpr1.combined.gtf.tmap"
    print >> sys.stderr, "Cuffcmpare all assemblies GTFs : filter c"
    selected_ids= set([])
    f_tmap = open(tmap)
    out = open("cuffcmpr1_selectedIds.txt", "w")
    for line in f_tmap:
        line = line.strip()
        cols = line.split('\t')
        if len(cols) < 5:
            continue
        class_code = cols[2]
        name =cols[4]
        if class_code != "c" :
            print >> out, name
        selected_ids.add(name)

    global output_dir
    asm_dir = output_dir + "merged_asm/"
    print >> sys.stderr, asm_dir
    if os.path.exists(asm_dir):
        pass
    else:
        os.mkdir(asm_dir)
    current_asm_gtf = "cuffcmpr1.combined.gtf"
    select_gtf(current_asm_gtf, selected_ids, "merged_asm/transcripts.gtf")

def get_version():
    return "0.0.1"

def main(argv=None):
    
    warnings.filterwarnings("ignore", "tmpnam is a potential security risk")
    global params
    params = TestParams()
    
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "ho:v", ["help", "output="])
        except getopt.error, msg:
            raise Usage(msg)
    
        # option processing
        for option, value in opts:
            if option == "-v":
                verbose = True
            if option in ("-h", "--help"):
                raise Usage(help_message)
            if option in ("-o", "--output"):
                output = value
        
        #if len(args) < 2:
        #    raise Usage(help_message)
           
        global run_log
        global run_cmd

        print >> sys.stderr
        print >> sys.stderr, "[%s] Beginning transcriptome build (suite v%s)" % (right_now(), get_version())
        print >> sys.stderr, "-----------------------------------------------"
        print >> sys.stderr
        
        start_time = datetime.now()
        prepare_output_dir()
        
        run_log = open(logging_dir + "run.log", "w", 0)
        run_cmd = " ".join(argv)
        print >> run_log, run_cmd
        
        transfrag_list_file = open(args[0], "r")

        if params.ref_gtf != None:
            test_input_files([params.ref_gtf])
        else:
            print >> sys.stderr, "Warning: no reference GTF provided!"

        # Check that all the primary assemblies are accessible before starting the time consuming stuff
        gtf_input_files = test_input_files(transfrag_list_file)
        
        #Meta assembly option:
        global run_meta_assembly
        if run_meta_assembly == 1:
            print >> sys.stderr, "Run Meta-Assembly \n"
            # Convert the primary assemblies to SAM format
            sam_input_files = convert_gtf_to_sam(gtf_input_files)

            # Merge the primary assembly SAMs into a single input SAM file
            merged_sam_filename = merge_sam_inputs(sam_input_files)

            # Run cufflinks on the primary assembly transfrags to generate a meta-assembly
            cufflinks(params, "merged_asm", merged_sam_filename)
        #Meta Cuffcompare option:
        else:
            cuffcompare_all_assemblies(gtf_input_files);
        
    
    except Usage, err:
        print >> sys.stderr, sys.argv[0].split("/")[-1] + ": " + str(err.msg)
        return 2


if __name__ == "__main__":
    sys.exit(main())