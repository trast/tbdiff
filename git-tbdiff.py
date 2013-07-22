#!/usr/bin/python2

# git-tbdiff: show the difference between two versions of a topic branch
#
# Copyright (c) 2013, Thomas Rast <trast@inf.ethz.ch>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import hungarian # https://pypi.python.org/pypi/hungarian
import tempfile
import subprocess
import difflib
import numpy as np
import optparse
from collections import defaultdict

parser = optparse.OptionParser()
parser.add_option('--color', default=True, action='store_true', dest='color')
parser.add_option('--no-color', action='store_false', dest='color')
parser.add_option('--dual-color', action='store_const', dest='color', const=2,
                  help='color both diff and diff-between-diffs')
parser.add_option('--no-patches', action='store_false', dest='patches', default=True,
                  help='short format (no diffs)')
parser.add_option('--creation-weight', action='store',
                  dest='creation_fudge', type=float, default=0.6,
                  help='Fudge factor by which creation is weighted [%default]')

def die(msg):
    print >>sys.stderr, msg
    sys.exit(1)

def strip_uninteresting_patch_parts(lines):
    out = []
    state = 'head'
    for line in lines:
        if line.startswith('diff --git'):
            state = 'diff'
            out.append('\n')
            out.append(line)
        elif state == 'head':
            if line.startswith('Author: '):
                out.append(line)
                out.append('\n')
            elif line.startswith('    '):
                out.append(line)
        elif state == 'diff':
            if line.startswith('index '):
                pass # skip
            elif line.startswith('@@ '):
                out.append('@@\n')
            elif line == '\n':
                # A completely blank (not ' \n', which is context)
                # line is not valid in a diff.  We skip it silently,
                # because this neatly handles the blank separator line
                # between commits in git-log output.
                pass
            else:
                out.append(line)
            continue
    return out

def read_patches(rev_list_args):
    series = []
    diffs = {}
    p = subprocess.Popen(['git', 'log', '--no-color', '-p', '--no-merges',
                          '--reverse', '--date-order']
                         + rev_list_args,
                         stdout=subprocess.PIPE)
    sha1 = None
    data = []
    def handle_commit():
        if sha1 is not None:
            series.append(sha1)
            diffs[sha1] = strip_uninteresting_patch_parts(data)
            del data[:]
    for line in p.stdout:
        if line.startswith('commit '):
            handle_commit()
            _, sha1 = line.strip().split()
            continue
        data.append(line)
    handle_commit()
    p.wait()
    return series, diffs


def strip_to_diff_parts_1(lines):
    in_diff = False
    for line in lines:
        if line.startswith('diff --git'):
            in_diff = True
        if not in_diff:
            continue
        if line.startswith('@@ '):
            continue
        yield line
def strip_to_diff_parts(*args, **kwargs):
    return list(strip_to_diff_parts_1(*args, **kwargs))


def diffsize(lA, lB):
    if not lA:
        return len(strip_to_diff_parts(lB))
    if not lB:
        return len(strip_to_diff_parts(lA))
    lA = strip_to_diff_parts(lA)
    lB = strip_to_diff_parts(lB)
    diff = difflib.unified_diff(lA, lB)
    return len(list(diff))


def commitinfo(sha1, fmt=None):
    return subprocess.check_output(['git', 'log', '--no-color', '--no-walk', '--pretty=format:%h %s', sha1]).strip().split(' ', 1)



c_reset = ''
c_commit = ''
c_frag = ''
c_old = ''
c_new = ''
c_inv_old = ''
c_inv_new = ''

def get_color(varname, default):
    return subprocess.check_output(['git', 'config', '--get-color', varname, default])

def invert_ansi_color(color):
    # \e[7;...m chooses the inverse of \e[...m
    # we try to be nice and also support the reverse transformation
    # (from inverse to normal)
    assert color[:2] == '\x1b['
    i = color.find('7;')
    if i >= 0:
        return color[:i] + color[i+2:]
    return '\x1b[7;' + color[2:]

def load_colors():
    global c_reset, c_commit, c_frag, c_new, c_old, c_inv_old, c_inv_new
    c_reset = get_color('', 'reset')
    c_commit = get_color('color.diff.commit', 'yellow dim')
    c_frag = get_color('color.diff.frag', 'magenta')
    c_old = get_color('color.diff.old', 'red')
    c_new = get_color('color.diff.new', 'green')
    c_inv_old = invert_ansi_color(c_old)
    c_inv_new = invert_ansi_color(c_new)

def commitinfo_maybe(cmt):
    if cmt:
        sha, subj = commitinfo(cmt)
    else:
        sha = 7*'-'
        subj = ''
    return sha, subj

def format_commit_line(i, left, j, right, has_diff=False):
    left_sha, left_subj = commitinfo_maybe(left)
    right_sha, right_subj = commitinfo_maybe(right)
    assert left or right
    if left and not right:
        color = c_old
        status = '<'
    elif right and not left:
        color = c_new
        status = '>'
    elif has_diff:
        color = c_commit
        status = '!'
    else:
        color = c_commit
        status = '='
    fmt = '%s' # color
    args = [color]
    # left coloring
    if status == '!':
        fmt += c_reset + c_old
    # left num
    fmt += numfmt if left else numdash
    args += [i+1] if left else []
    # left hash
    fmt += ": %8s"
    args += [left_sha]
    if status == '!':
        fmt += c_reset + color
    # middle char
    fmt += " %s "
    args += [status]
    # right coloring
    if status == '!':
        fmt += c_reset + c_new
    # right num
    fmt += numfmt if right else numdash
    args += [j+1] if right else []
    # right hash
    fmt += ": %8s"
    args += [right_sha]
    if status == '!':
        fmt += c_reset + color
    # subject
    fmt += " %s"
    args += [right_subj if right else left_subj]
    #
    fmt += "%s"
    args += [c_reset]
    print fmt % tuple(args)

def compute_matching_assignment(sA, dA, sB, dB):
    la = len(sA)
    lb = len(sB)
    dist = np.zeros((la+lb, la+lb), dtype=np.uint32)
    for i,u in enumerate(sA):
        for j,v in enumerate(sB):
            dist[i,j] = diffsize(dA[u], dB[v])
    # print dist
    for i,u in enumerate(sA):
        for j in range(lb, lb+la):
            dist[i,j] = options.creation_fudge*diffsize(dA[u], None)
    for i in range(la, la+lb):
        for j,v in enumerate(sB):
            dist[i,j] = options.creation_fudge*diffsize(None, dB[v])
    lhs, rhs = hungarian.lap(dist)
    return lhs, rhs

def split_away_same_patches(sA, dA, sB, dB):
    patchesB = defaultdict(list)
    for j,v in enumerate(sB):
        patchesB[tuple(dB[v])].append(j)
    eqA = []
    eqB = [None] * len(sB)
    for i,u in enumerate(sA):
        patch = tuple(dA[u])
        try:
            j = patchesB[patch].pop(0)
        except IndexError:
            eqA.append(None)
            continue
        eqA.append(j)
        eqB[j] = i
    return eqA, eqB

def make_index_map(eqlist, othereqlist):
    imap = []
    mapped = 0
    for orig,eq in enumerate(eqlist):
        if eq is None:
            imap.append(mapped)
        mapped += 1
    imap.extend(range(mapped, mapped+sum(1 for x in othereqlist if x is None)))
    return imap

def rebuild_match_list(eqlist, matchlist, imap):
    out = []
    match_it = iter(matchlist)
    for i,eq in enumerate(eqlist):
        if eq is None:
            matched = match_it.next()
            out.append(imap[matched])
        else:
            out.append(eq)
    for i in match_it:
        out.append(imap[i])
    return out

def compute_assignment(sA, dA, sB, dB):
    pmap = []
    la = len(sA)
    lb = len(sB)

    # Attempt to greedily assign an exact match with 0 weight (and
    # give the other choices for this commit a very large weight).
    # This speeds up the case where the patches are the same.
    eqA, eqB = split_away_same_patches(sA, dA, sB, dB)
    lhs1, rhs1 = compute_matching_assignment([u for u,e in zip(sA,eqA) if e is None], dA,
                                             [v for v,e in zip(sB,eqB) if e is None], dB)
    imap = make_index_map(eqA, eqB)
    jmap = make_index_map(eqB, eqA)
    lhs = np.array(rebuild_match_list(eqA, lhs1, jmap))
    rhs = np.array(rebuild_match_list(eqB, rhs1, imap))

    # We assume the user is really more interested in the second
    # argument ("newer" version).  To that end, we print the output in
    # the order of the RHS.  To put the LHS commits that are no longer
    # in the RHS into a good place, we place them once we have seen
    # all of their predecessors in the LHS.
    new_on_lhs = (lhs >= lb)[:la]
    lhs_prior_counter = np.arange(la)

    def process_lhs_orphans():
        while True:
            assert (lhs_prior_counter >= 0).all()
            w = (lhs_prior_counter == 0) & new_on_lhs
            idx = w.nonzero()[0]
            if len(idx) == 0:
                break
            pmap.append((idx[0], None, None))
            new_on_lhs[idx[0]] = False
            lhs_prior_counter[idx[0]+1:] -= 1

    for j,(u,i) in enumerate(zip(sB, rhs)):
        # now show an RHS commit
        process_lhs_orphans()
        if i < la:
            idiff = list(difflib.unified_diff(dA[sA[i]], dB[u]))
            pmap.append((i, j, idiff))
            lhs_prior_counter[i+1:] -= 1
        else:
            pmap.append((None, j, None))
    process_lhs_orphans()

    return pmap

def print_colored_interdiff(idiff):
    for line in idiff:
        line = line.rstrip('\n')
        if not line:
            print
            continue
        # Hunk headers in interdiff are always c_frag, and hunk
        # headers in the original patches are left uncolored (too
        # noisy).
        if line.startswith('@@'):
            print "    %s%s%s" % (c_frag, line, c_reset)
            continue
        # In traditional single-coloring mode, we color according to
        # the interdiff.
        if options.color == True:
            color = ''
            if line.startswith('-'):
                color = c_old
            elif line.startswith('+'):
                color = c_new
            print ''.join(["    ", color, line, c_reset])
            continue
        # In dual-color mode, we color the first column (changes
        # between patches) in reverse to highlight the interdiff, and
        # the rest of the line (the actual patches) normally to
        # highlight the diffs themselves.
        lead, line = line[0], line[1:]
        lead_color = ''
        if lead == '+':
            lead_color = c_inv_new
        elif lead == '-':
            lead_color = c_inv_old
        main_color = ''
        if line.startswith('+'):
            main_color = c_new
        elif line.startswith('-'):
            main_color = c_old
        print ''.join(["    ",
                       lead_color, lead, c_reset,
                       main_color, line, c_reset])

def prettyprint_assignment(sA, dA, sB, dB):
    assignment = compute_assignment(sA, dA, sB, dB)
    for i, j, idiff in assignment:
        if j is None:
            format_commit_line(i, sA[i], None, None)
        elif i is None:
            format_commit_line(None, None, j, sB[j])
        elif len(idiff) == 0:
            format_commit_line(i, sA[i], j, sB[j], has_diff=False)
        else:
            format_commit_line(i, sA[i], j, sB[j], has_diff=True)
            if options.patches:
                print_colored_interdiff(idiff[2:]) # starts with --- and +++ lines


if __name__ == '__main__':
    options, args = parser.parse_args()
    if options.color:
        load_colors()
    if len(args) == 2 and '..' in args[0] and '..' in args[1]:
        rangeA = [args[0]]
        rangeB = [args[1]]
    elif len(args) == 1 and '...' in args[0]:
        A, B = args[0].split("...", 1)
        rangeA = [A, '--not', B]
        rangeB = [B, '--not', A]
    elif len(args) == 3:
        rangeA = [args[1], '--not', args[0]]
        rangeB = [args[2], '--not', args[0]]
    else:
        die("usage: %(command)s A..B C..D\n"
            "   or: %(command)s A...B         # short for:  B..A A..B\n"
            "   or: %(command)s base A B      # short for:  base..A base..B" %
            {'command' : sys.argv[0]})
    sA, dA = read_patches(rangeA)
    sB, dB = read_patches(rangeB)
    la = len(sA)
    lb = len(sB)
    numwidth = max(len(str(la)), len(str(lb)))
    numfmt = "%%%dd" % numwidth
    numdash = numwidth*'-'
    prettyprint_assignment(sA, dA, sB, dB)
