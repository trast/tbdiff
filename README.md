git-tbdiff: topic branch interdiff
==================================

### 2-minute guide

Installation:

    cp git-tbdiff.py /usr/local/bin/git-tbdiff
    # or anywhere else in $PATH, or in $(git --exec-path)

If your system does not yet have a `/usr/bin/python2` symlink (older
systems would only have `/usr/bin/python`), you will need to edit the
`#!` line.

Usage:

    git tbdiff A..B C..D

to compare the topic branch represented by the range A..B with that in
the range C..D.

or:

    git tbdiff A...B

to let tbdiff automatically calculate the common ancestor X and
compare the range X..A to X..B.

### Synopsis

    git tbdiff [--[no-]color] [--no-patches]
               [--creation-weight=<factor>]
               <range1> <range2>

    git tbdiff [--[no-]color] [--no-patches]
               [--creation-weight=<factor>]
               <committish1>...<committish2>

    git tbdiff [--[no-]color] [--no-patches]
               [--creation-weight=<factor>]
               <base> <topic1> <topic2>

### Description

_tbdiff_ shows the differences between two versions of a patch series,
or more generally, two sets of commits (ignoring merges).
To do this in a meaningful way, it tries to find a good correspondence
between commits in the two versions (see _Algorithm_ below), and then
shows the difference between the pairs found.  It also copes with
removal and addition of commits.

The two `<range>` arguments are passed unchanged and without any
validation to two git-log invocations.


### Options

* `--[no-]color`

  Toggle colored output.  The default is to use color.

* `--no-patches`

  Suppress the diffs between commit pairs that were deemed to
  correspond; only show the pairings.

* `--creation-weight=<factor>`

  Set the creation/deletion cost fudge factor to `<factor>`.
  Defaults to 0.6.  Try a larger value if _tbdiff_ erroneously
  considers a large change a total rewrite (deletion of one
  commit and addition of another), and a smaller one in the
  reverse case.  See the _Algorithm_ section below for an
  explanation why this is needed.


### Rationale

Git does not ship with convenient tools for seeing the difference
between versions of a topic branch.  Some approaches seen in the wild
include:

* use git-cherry as a first-order comparison

* rebase the old version on the new version to a) have the patch-id
  logic drop equivalent patches and b) [usually] get a conflict when
  the patches themselves differ on a change

* apply on the same base

* run interdiffs across the series

* run an interdiff of the "squashed diff" (base to branch)

We propose a somewhat generalized approach based on interdiffs.  The
goal would be to find an explanation of the new series in terms of the
old one.  However, the order might be different, some commits could
have been added and removed, and some commits could have been tweaked.


### Algorithm

The general idea is this:

Suppose the old version has commits 1--2 and the new one has commits
A--C.  Assume that A is a cherry-pick of 2, and C is a cherry-pick of
1 but with a small modification (say, a fixed typo).  Visualize the
commits as a bipartite graph:

    1            A

    2            B

                 C

We are looking for a "best" explanation of the new series in terms of
the old one.  We can represent an "explanation" as an edge in the
graph:


    1            A
               /
    2 --------'  B

                 C

The 0 represents the edge weight; the explanation is "free" because
there was no change.  Similarly C can be explained using 1, but it has
some cost c>0 because of the modification:


    1 ----.      A
          |    /
    2 ----+---'  B
          |
          `----- C
          c>0

Clearly what we are looking for is some sort of a minimum cost
bipartite matching; 1 is matched to C at some cost, etc.  The
underlying graph is in fact a complete bipartite graph; the cost we
associate with every edge is the size of the interdiff between the two
commits in question.  To also explain new commits, we introduce dummy
commits on both sides:

    1 ----.      A
          |    /
    2 ----+---'  B
          |
    o     `----- C
          c>0
    o            o

    o            o

The cost of an edge o--C is the size of C's diff, modified by a fudge
factor that should be smaller than 1.  The cost of an edge o--o is
free.  The fudge factor is necessary because even if 1 and C have
nothing in common, they may still share a few empty lines and such,
making the assignment "1--C, o--o" may be slightly cheaper than "1--o,
o--C" even if 1 and C have nothing in common.  With the fudge factor
we require a much larger common part to consider the patches related.

This definition allows us to find a "good" topic interdiff among
topics with n and m commits in the time needed to compute n+m commit
diffs and then n*m interdiffs, plus the time needed to compute the
matching.  For example, in this Python version we use the hungarian[1]
package, where the underlying algorithm runs in O(n^4)[2].   The
matching found in this case will be like

    1 ----.      A
          |    /
    2 ----+---'  B
       .--+-----'
    o -'  `----- C
          c>0
    o ---------- o

    o ---------- o

Then we reconstruct a "pretty" (well, not quite) output that
represents the topic diff.



[1]  https://pypi.python.org/pypi/hungarian

[2]  http://en.wikipedia.org/wiki/Hungarian_algorithm
