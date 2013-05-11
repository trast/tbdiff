#!/usr/bin/python

import os
import sys
import hungarian # https://pypi.python.org/pypi/hungarian
import tempfile
import subprocess
import difflib
import numpy as np


def die(msg):
    print >>sys.stderr, msg
    sys.exit(1)

def prepare_patches(rev_list_arg):
    tmpdir = tempfile.mkdtemp()
    ret = subprocess.call(["git", "format-patch", "-o", tmpdir, rev_list_arg],
                          stdout=open('/dev/null', 'w'))
    if ret:
        die("git format-patch %s returned %d" % (rev_list_arg, ret))
    return tmpdir


def strip_uninteresting_mail_parts(lines):
    out = []
    state = 'head'
    for line in lines:
        if state == 'ddd' and line.startswith('diff --git'):
            state = 'diff'
        elif state == 'head' and line.strip() == '':
            state = 'msg'
        elif state == 'msg' and line.strip() == '---':
            state = 'ddd'
        if state in ('diff', 'msg'):
            if line.startswith('index '):
                pass # skip
            elif line.startswith('@@ '):
                out.append('@@\n')
            else:
                out.append(line)
            continue
        elif state == 'head' and (line.startswith('From:')
                                or line.startswith('Subject:')):
            out.append(line)
            continue
    return out

def read_patches(rev_list_arg):
    series = []
    diffs = {}
    tmpdir = prepare_patches(rev_list_arg)
    for name in os.listdir(tmpdir):
        fp = open(os.path.join(tmpdir, name), 'r')
        data = fp.readlines()
        sha1 = data[0].split()[1]
        series.append(sha1)
        diffs[sha1] = strip_uninteresting_mail_parts(data)
    subprocess.call(['rm', '-rf', tmpdir])
    return series, diffs


def strip_to_diff_parts(lines):
    in_diff = False
    for line in lines:
        if line.startswith('diff --git'):
            in_diff = True
        if not in_diff:
            continue
        if line.startswith('@@ '):
            continue
        yield line


def diffsize(lA, lB):
    if not lA:
        return len(lB)
    if not lB:
        return len(lA)
    lA = list(strip_to_diff_parts(lA))
    lB = list(strip_to_diff_parts(lB))
    diff = difflib.unified_diff(lA, lB)
    return len(list(diff))


def puterr(data):
    sys.stderr.write(data)
    sys.stderr.flush()


def oneliner(sha1):
    return subprocess.check_output(['git', 'log', '--no-walk', '--oneline', sha1]).strip()


if __name__ == '__main__':
    if len(sys.argv) != 3:
        die("usage: %s A..B C..D" % sys.argv[0])
    sA, dA = read_patches(sys.argv[1])
    sB, dB = read_patches(sys.argv[2])
    la = len(sA)
    lb = len(sB)
    dist = np.zeros((la+lb, la+lb), dtype=np.uint32)
    for i,u in enumerate(sA):
        puterr('.')
        for j,v in enumerate(sB):
            dist[i,j] = diffsize(dA[u], dB[v])
    puterr('\n')
    for i,u in enumerate(sA):
        for j in range(lb, lb+la):
            dist[i,j] = diffsize(dA[u], None)
    for i in range(la, la+lb):
        for j,v in enumerate(sB):
            dist[i,j] = diffsize(None, dB[v])
    lhs, rhs = hungarian.lap(dist)
    for i,(v,j) in enumerate(zip(sA, lhs)):
        if i > 0:
            print
        print "commit %d: %s" % (i+1, oneliner(v))
        if j < lb:
            print "    matches commit %d: %s" % (j+1, oneliner(sB[j]))
            idiff = list(difflib.unified_diff(dA[v], dB[sB[j]]))
            if idiff:
                print "    interdiff:"
                for line in idiff[2:]:
                    print "        " + line,
        else:
            print "    newly added in left side"
    for j,(u,i) in enumerate(zip(sB, rhs)):
        if i < la:
            continue
        print
        print "newly added in right side"
        print "    commit %d: %s" % (j+1, oneliner(u))
