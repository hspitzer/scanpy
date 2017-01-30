# Copyright 2016-2017 F. Alexander Wolf (http://falexwolf.de).
"""
Diffusion Pseudotime Analysis
=============================

Perform Diffusion Pseudotime analysis of an expression matrix, given the
expression vector of an "initial state" = "root cell".

Reference
---------
Diffusion Pseudotime: Haghverdi et al., Nature Methods 13, 3971 (2016).

See also
--------
- Diffusion Maps: Coifman et al., PNAS 102, 7426 (2005).
- Diffusion Maps applied to single-cell data: Haghverdi et al., Bioinformatics
  31, 2989 (2015).
- Diffusion Maps as a flavour of spectral clustering: von Luxburg,
  arXiv:0711.0189 (2007).
"""   

# standard modules
from collections import OrderedDict as odict
# scientific modules
import numpy as np
import scipy as sp
import matplotlib
from ..compat.matplotlib import pyplot as pl
# scanpy modules
from .. import settings as sett
from .. import plotting as plott
from .. import utils
from .. import graph

def dpt(ddata, num_branchings=1, k=5, knn=False, 
        sigma=0, allow_branching_at_root=False):
    """
    Perform DPT analsysis as of Haghverdi et al. (2016).

    Reference
    ---------
    Diffusion Pseudotime: Haghverdi et al., Nature Methods 13, 3971 (2016).

    Parameters
    ----------
    ddata : dict containing
        X : np.ndarray
            Data array, rows store observations, columns variables.
        xroot : np.ndarray
            Root of stochastic process on data points (root cell), specified
            either as expression vector of shape X.shape[1] or as index. The
            latter is not recommended.
    num_branchings : int, optional (default: 1)
        Number of branchings to detect.
    k : int, optional (default: 5)
        Specify the number of nearest neighbors in the knn graph. If knn ==
        False, set the Gaussian kernel width to the distance of the kth
        neighbor (method 'local').
    knn : bool, optional (default: False)
        If True, use a hard threshold to restrict the number of neighbors to
        k, that is, consider a knn graph. Otherwise, use a Gaussian Kernel
        to assign low weights to neighbors more distant than the kth nearest
        neighbor.
    sigma : float, optional (default: 0)
        If greater 0, ignore parameter 'k', but directly set a global width
        of the Kernel Gaussian (method 'global').
    allow_branching_at_root : bool, optional (default: False)
        Allow to have branching directly at root point.
        
    Returns
    -------
    ddpt : dict containing
        pseudotimes : np.ndarray
            Array of dim (number of cells) that stores the pseudotime of each
            cell, that is, the DPT distance with respect to the root cell.
        groupmasks : np.ndarray
            Array of dim (number of groups) x (number of cells). In the rows, it
            contains one-dimensional mask arrays that store the index sets that
            correspond to subgroups detected by the 'branch detection'
            algorithm.
        groupnames : np.ndarray
            Array of dimension (number of groups) that stores group names in the
            order they appear in groupsmasks.
        groupids_n : np.ndarray of dtype int
            Array of dim (number of cells) that stores the segment=subgroup id -
            an integer that indexes groupnames - of each cell. The groups might
            either correspond to 'progenitor cells', 'undecided cells' or
            'branches'.
        Y : np.ndarray
            Array of shape (number of samples) x (number of eigen
            vectors). DiffMap representation of data, which is the right eigen
            basis of transition matrix with eigenvectors as columns.
        evals : np.ndarray
            Array of size (number of cells). Eigenvalues of transition matrix.
    """
    params = locals(); del params['ddata']
    X = ddata['X']
    xroot = ddata['xroot']
    dpt = DPT(X, params)
    # diffusion map
    ddpt = dpt.diffmap()
    sett.m(0,'perform Diffusion Pseudotime Analysis')
    # compute M matrix of cumulative transition probabilities,
    # see Haghverdi et al. (2016)
    dpt.compute_M_matrix()
    # compute DPT distance matrix, which we refer to as 'Ddiff'
    dpt.compute_Ddiff_matrix()
    # set root point, if it's a gene expression value, first locate the root
    if type(xroot) == np.ndarray:
        dpt.find_root(xroot)
    # if it's an index, directly set the index
    else:
        dpt.iroot = xroot
    ddpt['iroot'] = np.array([dpt.iroot])
    # pseudotimes are distances from root point
    dpt.set_pseudotimes()
    ddpt['pseudotimes'] = dpt.pseudotimes
    # detect branchings and partition the data into segments
    dpt.branchings_segments()
    # as in every tool or data annotation, we define (sub)groups
    ddpt['groupmasks'] = dpt.segs # array of shape (number of groups x number of samples)
                                  # it's an array of mask arrays
    ddpt['groupids_n'] = dpt.segslabels # array of shape (number of samples)
    # store the group labels and default colors in the order they appear in 'groups'
    ddpt['groupids'] = np.arange(len(ddpt['groupmasks']), dtype=int)
    ddpt['groupnames'] = [str(i) for i in ddpt['groupids']]
    # n-vector of groupnames
    ddpt['groupnames_n'] = [ddpt['groupnames'][i] if i < len(ddpt['groupnames'])
                           else 'dontknow'
                           for i in ddpt['groupids_n']]

    # the ordering according to segments and pseudotimes
    ddpt['indices'] = dpt.indices
    ddpt['changepoints'] = dpt.changepoints
    ddpt['segtips'] = dpt.segstips
    # type of dict
    ddpt['type'] = 'dpt'    
    return ddpt

def plot(ddpt, ddata,
         comps='1,2,3',
         layout='2d',
         legendloc='lower right',
         cmap='jet'): # consider changing to 'viridis'
    """
    Plot the results of a DPT analysis.

    Parameters
    ----------
    ddpt : dict
        Dict returned by DPT tool.
    ddata : dict
        Data dictionary.
    comps : str
         String in the form "comp1,comp2,comp3".
    layout : {'2d', '3d', 'unfolded 3d'}, optional (default: '2d')
         Layout of plot.
    legendloc : see matplotlib.legend, optional (default: 'lower right') 
         Options for keyword argument 'loc'.
    cmap : str, optional (default: jet)
         String denoting matplotlib color map. 
    """
    params = locals(); del params['ddata']; del params['ddpt']
    X = ddata['X']
    ddpt['groupcolors'] = pl.cm.get_cmap(params['cmap'])(
                                         pl.Normalize()(ddpt['groupids']))

    # color by pseudotime and by segments
    colors = [ddpt['pseudotimes'], 'white']
    # coloring according to experimental labels
    if 'groupmasks' in ddata:
        colors.append('grey')
    # highlight root
    highlights = list(ddpt['iroot'])
    # highlight tip points of each segment
    if False:
        highlights = [i for l in ddpt['segtips'] for i in l if l[0] != -1]

    # a single figure for all colors using 2 diffusion components
    plot_groups(ddpt, ddata, params, colors, highlights)

    # plot segments and pseudotimes
    plot_segments_pseudotimes(ddpt, params['cmap'])

    # if number of genes is not too high, plot the time series
    if X.shape[1] <= 11:
        # plot time series as gene expression vs time
        plott.timeseries(X[ddpt['indices']],ddata['colnames'],
                         highlightsX=ddpt['changepoints'],
                         xlim=[0,1.3*X.shape[0]])
        if sett.savefigs:
            pl.savefig(sett.figdir+ddpt['writekey']+'_vsorder.'+sett.extf)
    elif X.shape[1] < 50:
        # plot time series as heatmap, as in Haghverdi et al. (2016), Fig. 1d
        plott.timeseries_as_heatmap(X[ddpt['indices'],:40],ddata['colnames'],
                                    highlightsX=ddpt['changepoints'])
        if sett.savefigs:
            pl.savefig(sett.figdir+ddpt['writekey']+'_heatmap.'+sett.extf)

    if not sett.savefigs and sett.autoshow:
        pl.show()
            

def plot_groups(ddpt, ddata, params, colors,
                highlights=[], highlights_labels=[]):
    """
    Plot groups in diffusion map visualization.
    """
    from numpy import array
    comps = array(params['comps'].split(',')).astype(int) - 1

    # base figure
    axs = plott.scatter(ddpt['Y'][:, comps],
                        subtitles=['pseudotime','segments',
                                   'experimental groups'],
                        layout=params['layout'],
                        c=colors,
                        highlights=highlights,
                        highlights_labels=highlights_labels,
                        cmap=params['cmap'])

    # dpt groups (segments)
    for igroup, group in enumerate(ddpt['groupmasks']):
        plott.group(axs[1], igroup, ddpt, ddpt['Y'][:, comps], params['layout'])
    axs[1].legend(frameon=False, loc=params['legendloc'])

    # annotated groups in data dict
    if 'groupmasks' in ddata:
        for igroup, group in enumerate(ddata['groupmasks']):
            plott.group(axs[2], igroup, ddata, ddpt['Y'][:, comps], params['layout'])
        axs[2].legend(frameon=False, loc='center left', bbox_to_anchor=(1, 0.5))
        pl.subplots_adjust(right=0.8)

    if sett.savefigs:
        pl.savefig(sett.figdir+ddpt['writekey']+'_diffmap.'+sett.extf)

def plot_segments_pseudotimes(ddpt, cmap):
    """ 
    Helper function for plot.
    """
    pl.figure()
    pl.subplot(211)
    plott.timeseries_subplot(ddpt['groupids_n'][ddpt['indices'],np.newaxis],
                             c=ddpt['groupids_n'][ddpt['indices']],
                             highlightsX=ddpt['changepoints'],
                             ylabel='segments',
                             yticks=(np.arange(ddpt['groupmasks'].shape[0],dtype=int) if 
                                     ddpt['groupmasks'].shape[0] < 5 else None),
                             cmap=cmap)
    pl.subplot(212)
    plott.timeseries_subplot(ddpt['pseudotimes'][ddpt['indices'],np.newaxis],
                             c=ddpt['pseudotimes'][ddpt['indices']],
                             highlightsX=ddpt['changepoints'],
                             ylabel='pseudotime',
                             yticks=[0,1],
                             cmap=cmap)
    if sett.savefigs:
        pl.savefig(sett.figdir+ddpt['writekey']+'_segpt.'+sett.extf)

class DPT(graph.DataGraph):
    """
    Diffusion Pseudotime Class.
    """

    def branchings_segments(self):
        """ 
        Detect branchings and partition the data into corresponding segments.

        Detect all branchings up to params['num_branchings'].

        Writes
        ------
        segs : np.ndarray
            Array of dimension (number of segments) x (number of data
            points). Each row stores a mask array that defines a segment.
        segstips : np.ndarray
            Array of dimension (number of segments) x 2. Each row stores the
            indices of the two tip points of each segment.
        segslabels : np.ndarray
            Array of dimension (number of data points). Stores an integer label
            for each segment.
        """
        self.detect_branchings()
        self.check_segments()
        self.postprocess_segments()
        self.order_segments()
        self.set_segslabels()
        self.order_pseudotime()

    def select_segment(self,segs,segstips):
        """
        Out of a list of line segments, choose segment that has the most
        distant second data point.

        Assume the distance matrix Ddiff is sorted according to seg_idcs.
        Compute all the distances.

        Returns
        -------
        iseg : int
            Index identifying the position within the list of line segments.
        tips3 : int
            Positions of tips within chosen segment.
        """
        scores_tips = np.zeros((len(segs),4))
        allindices = np.arange(self.N,dtype=int)
        for iseg, seg in enumerate(segs):
            # do not consider 'unproper segments'
            if segstips[iseg][0] == -1:
                continue
            # restrict distance matrix to points in segment
            Dseg = self.Dchosen[np.ix_(seg,seg)]
            # obtain the two indices that maximize distance in the segment
            # call them tips
            if False:
                # obtain the position within the segment by searching for
                # the maximum
                tips = list(np.unravel_index(np.argmax(Dseg),Dseg.shape))
            if True:
                # map the global position to the position within the segment
                tips = [np.where(allindices[seg] == tip)[0][0]
                        for tip in segstips[iseg]]
            # find the third point on the segment that has maximal
            # added distance from the two tip points
            dseg = Dseg[tips[0]] + Dseg[tips[1]]
            # add this point to tips, it's a third tip, we store it at the first
            # position in an array called tips3
            tips3 = np.insert(tips,0,np.argmax(dseg))
            # compute the score as ratio of the added distance to the third tip,
            # to what it would be if it were on the straight line between the
            # two first tips, given by Dseg[tips[:2]]
            # if we did not normalize with, there would be a danger of simply
            # assigning the highest score to the longest segment
            score = dseg[tips3[0]]/Dseg[tips3[1],tips3[2]]
            # write result
            scores_tips[iseg,0] = score
            scores_tips[iseg,1:] = tips3
        iseg = np.argmax(scores_tips[:,0])
        tips3 = scores_tips[iseg,1:].astype(int)
        return iseg, tips3

    def detect_branchings(self):
        """ 
        Detect all branchings up to params['num_branchings'].

        Writes Attributes
        -----------------
        segs : np.ndarray
            List of integer index arrays.
        segstips : np.ndarray
            List of indices of the tips of segments.
        """
        sett.m(0,'detect',self.params['num_branchings'],'branchings')
        # a segment is a subset of points of the data set
        # it's completely defined by the indices of the points in the segment
        # initialize the search for branchings with a single segment,
        # that is, get the indices of the whole data set
        indices_all = np.arange(self.Dchosen.shape[0],dtype=int)
        # let's keep a list of segments, the first segment to add is the 
        # whole data set
        segs = [indices_all]
        # a segment can as well be defined by the two points that have maximal
        # distance in the segment, the "tips" of the segment 
        #
        # the rest of the points in the segment is then defined by demanding
        # them to "be close to the line segment that connects the tips", that
        # is, for such a point, the normalized added distance to both tips is
        # smaller than one:
        #     (D[tips[0],i] + D[tips[1],i])/D[tips[0],tips[1] < 1
        # of course, this condition is fulfilled by the full cylindrical
        # subspace surrounding that line segment, where the radius of the
        # cylinder can be infinite
        #
        # if D denotes a euclidian distance matrix, a line segment is a linear
        # object, and the name "line" is justified. if we take the
        # diffusion-based distance matrix Dchosen, which approximates geodesic
        # distance, with "line", we mean the shortest path between two points,
        # which can be highly non-linear in the original space
        #
        # let us define the tips of the whole data set
        tips_all = list(np.unravel_index(np.argmax(self.Dchosen),self.Dchosen.shape))
        # we keep a list of the tips of each segment
        segstips = [tips_all]
        for ibranch in range(self.params['num_branchings']):
            # out of the list of segments, determine the segment
            # that most strongly deviates from a straight line
            # and provide the three tip points that span the triangle
            # of maximally distant points
            iseg, tips3 = self.select_segment(segs,segstips)
            sett.m(0,'tip points',tips3,'= [third start end]')
            # detect branching and update segs and segstips
            segs, segstips = self.detect_branching(segs,segstips,iseg,tips3)
        # store as class members
        self.segs = segs
        self.segstips = segstips
        sett.mt(0,'finished branching detection')

    def postprocess_segments(self):
        """
        Convert the format of the segment class members.
        """
        # make segs a list of mask arrays, it's easier to store 
        # as there is a hdf5 equivalent
        for iseg,seg in enumerate(self.segs):
            mask = np.zeros(self.Dchosen.shape[0],dtype=bool)
            mask[seg] = True
            self.segs[iseg] = mask
        # convert to arrays
        self.segs = np.array(self.segs)
        self.segstips = np.array(self.segstips)
        
    def check_segments(self):
        """
        Perform checks on segments and sort them according to pseudotime.
        """
        # find the segment that contains the root cell
        for iseg,seg in enumerate(self.segs):
            if self.iroot in seg:
                isegroot = iseg
                break
        # check whether the root cell is one of the tip cells of the 
        # segment, if not we need to introduce a new branching, directly
        # at the root cell
        if self.iroot not in self.segstips[iseg]:
            # if it's not exactly a tip, but very close to it, 
            # just keep it as it is
            dist_to_root = self.Dchosen[self.iroot,self.segstips[iseg]]
            # otherwise, allow branching at root
            if (np.min(dist_to_root) > 0.01*self.Dchosen[tuple(self.segstips[iseg])]
                and self.params['allow_branching_at_root']):
                allindices = np.arange(self.N,dtype=int)
                tips3_global = np.insert(self.segstips[iseg],0,self.iroot)
                # map the global position to the position within the segment
                tips3 = np.array([np.where(allindices[self.segs[iseg]] == tip)[0][0]
                                  for tip in tips3_global])
                # detect branching and update self.segs and self.segstips
                self.segs, self.segstips = self.detect_branching(self.segs,
                                                                 self.segstips,
                                                                 iseg,tips3)            
        
    def order_segments(self):
        """
        Order segments according to average pseudotime.
        """ 
        # there are different options for computing the score
        if False:
            # minimum of pseudotimes in the segment
            score = np.min
        if True:
            # average pseudotime
            score = np.average
        # score segments by minimal pseudotime
        seg_scores = []
        for seg in self.segs:
            seg_scores.append(score(self.pseudotimes[seg]))
        indices = np.argsort(seg_scores)
        # order segments by minimal pseudotime
        self.segs = self.segs[indices]
        self.segstips = self.segstips[indices]
        # within segstips, order tips according to pseudotime
        for itips, tips in enumerate(self.segstips):
            if tips[0] != -1:
                indices = np.argsort(self.pseudotimes[tips])
                self.segstips[itips] = self.segstips[itips][indices]

    def set_segslabels(self):
        """
        Return a single array that stores integer segment labels.
        """
        segslabels = np.zeros(self.Dchosen.shape[0],dtype=int)
        for iseg,seg in enumerate(self.segs):
            segslabels[seg] = iseg
        self.segslabels = segslabels

    def order_pseudotime(self):
        """
        Define indices that reflect segment and pseudotime order.

        Writes
        ------
        indices : np.ndarray
            Index array of shape n, which stores an ordering of the data points
            with respect to increasing segment index and increasing pseudotime.
        changepoints : np.ndarray
            Index array of shape len(ssegs)-1, which stores the indices of
            points where the segment index changes, with respect to the ordering
            of indices.
        """ 
        # sort indices according to segments
        indices = np.argsort(self.segslabels)
        segslabels = self.segslabels[indices]
        # find changepoints of segments
        changepoints = np.arange(indices.size-1)[np.diff(segslabels)==1]+1
        pseudotimes = self.pseudotimes[indices]
        for iseg,seg in enumerate(self.segs):
            # only consider one segment, it's already ordered by segment
            seg_sorted = seg[indices]
            # consider the pseudotimes on this segment and sort them
            seg_indices = np.argsort(pseudotimes[seg_sorted])
            # within the segment, order indices according to increasing pseudotime
            indices[seg_sorted] = indices[seg_sorted][seg_indices]
        # define class members
        self.indices = indices
        self.changepoints = changepoints

    def detect_branching(self,segs,segstips,iseg,tips3):
        """ 
        Detect branching on given segment.

        Call function _detect_branching and perform bookkeeping on segs and
        segstips.

        Parameters
        ----------
        segs : list of np.ndarray
            Dchosen distance matrix restricted to segment.
        segstips : list of np.ndarray
            Stores all tip points for the segments in segs.
        iseg : int
            Position of segment under study in segs.
        tips3 : np.ndarray
            The three tip points. They form a 'triangle' that contains the data.
        
        Returns
        -------
        segs : list of np.ndarray
            Updated list of segments.
        segstips : list of np.ndarray
            Updated list of segstips.
        """
        seg = segs[iseg]
        # restrict distance matrix to points in chosen segment seg
        Dseg = self.Dchosen[np.ix_(seg,seg)]
        # given the three tip points and the distance matrix detect the
        # branching on the segment, return the list ssegs of segments that
        # are defined by splitting this segment
        ssegs, ssegs_tips = self._detect_branching(Dseg,tips3)            
        # map back to global indices
        for iseg_new,seg_new in enumerate(ssegs):
            ssegs[iseg_new] = seg[seg_new]
            if ssegs_tips[iseg_new][0] != -1:
                ssegs_tips[iseg_new] = seg[ssegs_tips[iseg_new]] 
        # remove previous segment
        segs.pop(iseg)
        segstips.pop(iseg)
        # append new segments
        segs += ssegs
        segstips += ssegs_tips
        return segs, segstips

    def _detect_branching(self,Dseg,tips):
        """ 
        Detect branching on given segment.

        Call function __detect_branching three times for all three orderings of
        tips. Points that do not belong to the same segment in all three
        orderings are assigned to a fourth segment. The latter is, by Haghverdi
        et al. (2016) referred to as 'undecided cells'.

        Parameters
        ----------
        Dseg : np.ndarray
            Dchosen distance matrix restricted to segment.
        tips : np.ndarray
            The three tip points. They form a 'triangle' that contains the data.
        
        Returns
        -------
        ssegs : list of np.ndarray
            List of segments obtained from splitting the single segment defined
            via the first two tip cells.
        ssegstips : list of np.ndarray
            List of tips of segments in ssegs.
        """
        if False:
            ssegs = self._detect_branching_versions(Dseg,tips)
        if True:
            ssegs = self._detect_branching_single(Dseg,tips)
        # make sure that each data point has a unique association with a segment
        masks = np.zeros((3,Dseg.shape[0]),dtype=bool)
        for iseg,seg in enumerate(ssegs):
            masks[iseg][seg] = True
        nonunique = np.sum(masks,axis=0) > 1
        # obtain the corresponding index arrays from masks
        ssegs = []
        for iseg,mask in enumerate(masks):
            mask[nonunique] = False
            ssegs.append(np.arange(Dseg.shape[0],dtype=int)[mask])
        # compute new tips within new segments
        ssegstips = []
        for inewseg, newseg in enumerate(ssegs):
            # get tip point position within segment
            tip = np.where(np.arange(Dseg.shape[0])[newseg]
                           == tips[inewseg])[0][0]
            # new tip within restricted distance matrix
            secondtip = np.argmax(Dseg[np.ix_(newseg,newseg)][tip])
            # map back to position within segment
            secondtip = np.arange(Dseg.shape[0])[newseg][secondtip]
            # add to list
            ssegstips.append([tips[inewseg],secondtip])
        # for the points that cannot be assigned to the three segments of the
        # branching, hence have no tip cells, but form a subset of their own,
        # add dummy tips [-1,-1]
        # this is not a good solution, but it ensures that we can easily write
        # to hdf5 as ssegstips can be transformed to np.ndarray with dtype = int
        ssegstips.append(np.array([-1,-1]))
        # the following would be preferrable, but then ssegstips results in 
        # a np.ndarray with dtype = object, for which there is no straight
        # forward hdf5 format, a solution via masks seems too much work
        #     ssegstips.append(np.array([],dtype=int))
        # also add the points not associated with a clear seg to ssegs
        mask = np.zeros(Dseg.shape[0],dtype=bool)
        # all points assigned to segments (flatten ssegs)
        mask[[i for l in ssegs for i in l]] = True
        # append all the points that have not been assigned. in Haghverdi et
        # al. (2016), we call them 'undecided cells'
        ssegs.append(np.arange(Dseg.shape[0],dtype=int)[mask==False])

        return ssegs, ssegstips

    def _detect_branching_single(self,Dseg,tips):
        """ 
        Detect branching on given segment.
        """
        # compute branchings using different starting points the first index of
        # tips is the starting point for the other two, the order does not
        # matter
        ssegs = []
        # permutations of tip cells
        ps = [[0,1,2], # start by computing distances from the first tip 
              [1,2,0], #             -"-                       second tip
              [2,0,1], #             -"-                       third tip
              ]
        for i,p in enumerate(ps):
            ssegs.append(self.__detect_branching(Dseg,
                                                 tips[p])[0])
        return ssegs

    def _detect_branching_versions(self,Dseg,tips):
        """ 
        Detect branching on given segment using three different versions.
        """
        # compute branchings using different starting points the first index of
        # tips is the starting point for the other two, the order does not
        # matter
        ssegs_versions = []
        # permutations of tip cells
        ps = [[0,1,2], # start by computing distances from the first tip 
              [1,2,0], #             -"-                       second tip
              [2,0,1], #             -"-                       third tip
              ]
        # invert permutations
        inv_ps = [[0,1,2],
                  [2,0,1],
                  [1,2,0],
                  ]
        for i,p in enumerate(ps):
            ssegs = self.__detect_branching(Dseg,
                                            tips[p])
            ssegs_versions.append(np.array(ssegs)[inv_ps[i]])
        ssegs = []
        # run through all three assignments of segments, and keep
        # only those assignments that were found in all three runs        
        for inewseg, newseg_versions in enumerate(np.array(ssegs_versions).T):
            if len(newseg_versions) == 3:
                newseg = np.intersect1d(np.intersect1d(newseg_versions[0],
                                                       newseg_versions[1]),
                                        newseg_versions[2])
            else:
                newseg = newseg_versions[0]
            ssegs.append(newseg)
        
        return ssegs
        
    def __detect_branching(self,Dseg,tips):
        """ 
        Detect branching on given segment.

        Compute point that maximizes kendall tau correlation of the sequences of
        distances to the second and the third tip, respectively, when 'moving
        away' from the first tip: tips[0]. 'Moving away' means moving in the
        direction of increasing distance from the first tip.

        Parameters
        ----------
        Dseg : np.ndarray
            Dchosen distance matrix restricted to segment.
        tips : np.ndarray
            The three tip points. They form a 'triangle' that contains the data.

        Returns
        -------
        ssegs : list of np.ndarray
            List of segments obtained from splitting the single segment defined
            via the first two tip cells.
        """
        # sort distance from first tip point
        idcs = np.argsort(Dseg[tips[0]])
        # then the sequence of distances Dseg[tips[0]][idcs] increases
        # consider now the sequence of distances from the other 
        # two tip points, which only increase when being close to tips[0]
        # where they become correlated
        # at the point where this happens, we define a branching point
        if True:
            imax = self.kendall_tau_split(Dseg[tips[1]][idcs],
                                             Dseg[tips[2]][idcs])
        if False:
            # if we were in euclidian space, the following should work
            # as well, but here, it doesn't because the scales in Dseg are
            # highly different, one would need to write the following equation
            # in terms of an ordering, such as exploited by the kendall 
            # correlation method above
            imax = np.argmin(Dseg[tips[0]][idcs] 
                                + Dseg[tips[1]][idcs]
                                + Dseg[tips[2]][idcs])
        # init list to store new segments
        ssegs = []
        # first new segment: all points until, but excluding the branching point
        ibranch = imax + 1
        # ibranch = int(0.95*imax) # more conservative here
        ssegs.append(idcs[:ibranch])
        # define nomalized distances to tip points for the rest of the data
        dist1 = Dseg[tips[1],idcs[ibranch:]]/Dseg[tips[1],idcs[ibranch-1]]
        dist2 = Dseg[tips[2],idcs[ibranch:]]/Dseg[tips[2],idcs[ibranch-1]]
        # assign points according to whether being closer to tip cell 1 or 2
        ssegs.append(idcs[ibranch:][dist1 <= dist2])
        ssegs.append(idcs[ibranch:][dist1 > dist2])

        return ssegs

    def kendall_tau_split(self,a,b):
        """
        Return splitting index that maximizes correlation in the sequences.

        Compute difference in Kendall tau for all splitted sequences. 

        For each splitting index i, compute the difference of the two
        correlation measures kendalltau(a[:i],b[:i]) and
        kendalltau(a[i:],b[i:]).

        Returns the splitting index that maximizes 
            kendalltau(a[:i],b[:i]) - kendalltau(a[i:],b[i:])        

        Parameters
        ----------
        a, b : np.ndarray
            One dimensional sequences. 

        Returns
        -------
        i : int
            Splitting index according to above description.
        """
        if a.size != b.size:
            raise ValueError('a and b need to have the same size')
        if a.ndim != b.ndim != 1:
            raise ValueError('a and b need to be one-dimensional arrays')            

        min_length = 5
        n = a.size
        idx_range = np.arange(min_length,a.size-min_length-1,dtype=int)
        corr_coeff = np.zeros(idx_range.size)
        pos_old = sp.stats.kendalltau(a[:min_length],b[:min_length])[0]
        neg_old = sp.stats.kendalltau(a[min_length:],b[min_length:])[0]
        for ii,i in enumerate(idx_range):
            if True:
                # compute differences in concordance when adding a[i] and b[i]
                # to the first subsequence, and removing these elements from
                # the second subsequence
                diff_pos, diff_neg = self._kendall_tau_diff(a,b,i)
                pos = pos_old + self._kendall_tau_add(i,diff_pos,pos_old)
                neg = neg_old + self._kendall_tau_subtract(n-i,diff_neg,neg_old)
                pos_old = pos
                neg_old = neg
            if False:
                # computation using sp.stats.kendalltau, takes much longer!
                # just for debugging purposes
                pos = sp.stats.kendalltau(a[:i+1],b[:i+1])[0]
                neg = sp.stats.kendalltau(a[i+1:],b[i+1:])[0]
            if False:
                # the following is much slower than using sp.stats.kendalltau,
                # it is only good for debugging because it allows to compute the
                # tau-a version, which does not account for ties, whereas
                # sp.stats.kendalltau computes tau-b version, which accounts for
                # ties
                pos = sp.stats.mstats.kendalltau(a[:i],b[:i],use_ties=False)[0]
                neg = sp.stats.mstats.kendalltau(a[i:],b[i:],use_ties=False)[0]
            corr_coeff[ii] = pos - neg
        iimax = np.argmax(corr_coeff)
        imax = min_length + iimax
        corr_coeff_max = corr_coeff[iimax]
        if corr_coeff_max < 0.3:
            sett.m(1,'  -> is root itself, never obtain significant correlation')
        return imax
        
    def _kendall_tau_add(self,len_old,diff_pos,tau_old):
        """
        Compute Kendall tau delta.

        The new sequence has length len_old + 1.

        Parameters
        ----------
        len_old : int
            The length of the old sequence, used to compute tau_old.
        diff_pos : int
            Difference between concordant and non-concordant pairs.
        tau_old : float
            Kendall rank correlation of the old sequence.
        """
        return 2./(len_old+1)*(float(diff_pos)/len_old-tau_old)

    def _kendall_tau_subtract(self,len_old,diff_neg,tau_old):
        """
        Compute Kendall tau delta.

        The new sequence has length len_old - 1.

        Parameters
        ----------
        len_old : int
            The length of the old sequence, used to compute tau_old.
        diff_neg : int
            Difference between concordant and non-concordant pairs.
        tau_old : float
            Kendall rank correlation of the old sequence.
        """
        return 2./(len_old-2)*(-float(diff_neg)/(len_old-1)+tau_old)

    def _kendall_tau_diff(self,a,b,i):
        """
        Compute difference in concordance of pairs in split sequences.

        Consider splitting a and b at index i.

        Parameters
        ----------
        a, b : np.ndarray

        Returns
        -------
        diff_pos, diff_neg : int, int
            Difference between concordant and non-concordant pairs for both
            subsequences.
        """
        # compute ordering relation of the single points a[i] and b[i] 
        # with all previous points of the sequences a and b, respectively
        a_pos = np.zeros(a[:i].size,dtype=int)
        a_pos[a[:i]>a[i]] = 1
        a_pos[a[:i]<a[i]] = -1
        b_pos = np.zeros(b[:i].size,dtype=int)
        b_pos[b[:i]>b[i]] = 1
        b_pos[b[:i]<b[i]] = -1
        diff_pos = np.dot(a_pos,b_pos).astype(float)
        
        # compute ordering relation of the single points a[i] and b[i] 
        # with all later points of the sequences
        a_neg = np.zeros(a[i:].size,dtype=int)
        a_neg[a[i:]>a[i]] = 1
        a_neg[a[i:]<a[i]] = -1
        b_neg = np.zeros(b[i:].size,dtype=int)
        b_neg[b[i:]>b[i]] = 1
        b_neg[b[i:]<b[i]] = -1
        diff_neg = np.dot(a_neg,b_neg)

        return diff_pos, diff_neg

def plot_subgroup(axs,ilabel,ddata,dscct,layout,cmap):
    """
    Plot experimental subgroup.
    """
    colors = pl.cm.get_cmap(cmap)(pl.Normalize()(range(len(ddata['poplabels']))))
    c = matplotlib.colors.rgb2hex(colors[ilabel])
    indices = ddata['explabels'] == ilabel
    indices = ddata['expindices'][indices]
    data = [dscct['rbasis'][indices,1],dscct['rbasis'][indices,2]]
    if layout == '3d':
        data.append(dscct['rbasis'][indices,3])
    axs[2].scatter(*data,c=c,edgecolors='face',
                   label=ddata['poplabels'][ilabel])

def plot_set(axs,iset,ddpt,layout):
    """
    Plot set.
    """
    set = ddpt['sets'][iset]
    c = matplotlib.colors.rgb2hex(ddpt['setcolors'][iset])
    data = [ddpt['rbasis'][set,1],ddpt['rbasis'][set,2]]
    if layout == '3d':
        data.append(ddpt['rbasis'][set,3])
    markersize = 3
    axs[1].scatter(*data,c=c,edgecolors='face',
                   s=markersize,
                   alpha=1,
                   label=ddpt['setlabels'][iset])

def plot_all_sets(ddpt,ddata,layout,colors,
                  highlights = [],
                  highlights_labels = [],
                  legendloc = 'lower right',
                  cmap= 'jet'): # consider changing to viridis
    """
    """
    # base figure
    axs = plott.diffmap(
        [ddpt['rbasis'][:, [1, 2, 3]]],
        layout=layout,
        c=colors,
        titles=['pseudotime', 'segments', 'experimental labels'],
        highlights=highlights,
        highlights_labels=highlights_labels,
        cmap=cmap,
    )

    # sets
    for iset,set in enumerate(ddpt['sets']):
        plot_set(axs,iset,ddpt,layout)
    axs[1].legend(frameon=False,loc=legendloc)

    # experimental subgroups
    if 'poplabels' in ddata:
        for ilabel,label in enumerate(ddata['poplabels']):
            plot_subgroup(axs, ilabel, ddata, ddpt, layout, cmap)
        if False:
            axs[2].legend(frameon=False,loc='lower right')
        if True:
            axs[2].legend(frameon=False,loc='center left',
                          bbox_to_anchor=(1, 0.5))
            pl.subplots_adjust(right=0.8)

    if sett.savefigs:
        pl.savefig(sett.figdir+ddpt['writekey']+'_diffmap.'+sett.extf)

def read_args(example_dict):
    """
    Read arguments for calling main from command line.
    """

    p = utils.default_parser(__doc__,example_dict)
    p = update_parser(p)
    args = utils.process_args(p)

    return args

def update_parser(p):
    """
    Update parser.
    """
    p = utils.add_args(p)
    return p