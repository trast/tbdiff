#!/usr/bin/python

import os
import sys
import hungarian # https://pypi.python.org/pypi/hungarian
import tempfile
import subprocess
import difflib
import numpy as np
import optparse

parser = optparse.OptionParser()
parser.add_option('--color', default=True, action='store_true', dest='color')
parser.add_option('--no-color', action='store_false', dest='color')

def die(msg):
    print >>sys.stderr, msg
    sys.exit(1)

def prepare_patches(rev_list_arg):
    tmpdir = tempfile.mkdtemp()
    ret = subprocess.call(["git", "format-patch", "-k", "-o", tmpdir, rev_list_arg],
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



c_reset = ''
c_commit = ''
c_frag = ''
c_old = ''
c_new = ''

def get_color(varname, default):
    return subprocess.check_output(['git', 'config', '--get-color', varname, default])

def load_colors():
    global c_reset, c_commit, c_frag, c_new, c_old
    c_reset = get_color('', 'reset')
    c_commit = get_color('color.diff.commit', 'yellow dim')
    c_frag = get_color('color.diff.frag', 'magenta')
    c_old = get_color('color.diff.old', 'red')
    c_new = get_color('color.diff.new', 'green')

if __name__ == '__main__':
    options, args = parser.parse_args()
    if options.color:
        load_colors()
    if len(args) != 2:
        die("usage: %s A..B C..D" % sys.argv[0])
    sA, dA = read_patches(args[0])
    sB, dB = read_patches(args[1])
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
    # We assume the user is really more interested in the second
    # argument ("newer" version).  To that end, we print the output in
    # the order of the RHS.  To put the LHS commits that are no longer
    # in the RHS into a good place, we place them once we have seen
    # all of their predecessors in the LHS.
    new_on_lhs = (lhs > lb)[:la]
    lhs_prior_counter = np.arange(la)
    for j,(u,i) in enumerate(zip(sB, rhs)):
        if j > 0:
            print
        # repeatedly show LHS-specific commits that had all their
        # predecessors shown
        while True:
            assert (lhs_prior_counter >= 0).all()
            w = (lhs_prior_counter == 0) & new_on_lhs
            idx = w.nonzero()[0]
            if not idx:
                break
            print "%s<%3d: %s%s" % (c_old, idx[0], sA[idx[0]], c_reset)
            print "    only in lhs"
            print
            new_on_lhs[idx[0]] = False
            lhs_prior_counter[idx[0]+1:] -= 1
        # now show an RHS commit
        if i < la:
            print "%s>%3d: %s%s" % (c_commit, j+1, oneliner(u), c_reset)
            print "%s<%3d: %s%s" % (c_commit, i+1, oneliner(sA[i]), c_reset)
            idiff = list(difflib.unified_diff(dA[sA[i]], dB[u]))
            if idiff:
                print "    interdiff:"
                for line in idiff[2:]: # starts with --- and +++ lines
                    c = ''
                    if line.startswith('+'):
                        c = c_new
                    elif line.startswith('-'):
                        c = c_old
                    elif line.startswith('@@'):
                        c = c_frag
                    print "        %s%s%s" % (c, line.rstrip('\n'), c_reset)
            lhs_prior_counter[i+1:] -= 1
        else:
            print "%s>%3d: %s%s" % (c_new, j+1, oneliner(u), c_reset)
            print "    only in rhs"
