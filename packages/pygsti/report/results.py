from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************
""" Defines the Results class."""

import collections as _collections
import itertools   as _itertools
import warnings    as _warnings
import time        as _time
import numpy       as _np

from ..             import construction         as _const
from ..             import objects              as _objs
from ..algorithms   import gaugeopt_to_target   as _gaugeopt_to_target
from ..tools        import listtools            as _lt
from ..             import tools                as _tools

#A flag to enable fast-loading of old results files (should
# only be changed by experts)
_SHORTCUT_OLD_RESULTS_LOAD = False

class Estimate(object):
    """
    A class encapsulating the `GateSet` objects related to 
    a single GST estimate up-to-gauge freedoms. 

    Thus, this class holds the "iteration" `GateSet`s leading up to a
    final `GateSet`, and then different gauge optimizations of the final
    set.
    """
    
    def __init__(self, parent, targetGateset=None, seedGateset=None,
                 gatesetsByIter=None, parameters=None):
        """
        Initialize an empty Estimate object.

        Parameters
        ----------
        parent : Results
            The parent Results object containing the dataset and
            gate string structure used for this Estimate.

        targetGateset : GateSet
            The target gateset used when optimizing the objective.

        seedGateset : GateSet
            The initial gateset used to seed the iterative part
            of the objective optimization.  Typically this is
            obtained via LGST.

        gatesetsByIter : list of GateSets
            The estimated gateset at each GST iteration. Typically these are the
            estimated gate sets *before* any gauge optimization is performed.

        parameters : dict
            A dictionary of parameters associated with how these gate sets
            were obtained.
        """
        self.parent = parent
        self.parameters = _collections.OrderedDict()
        self.goparameters = _collections.OrderedDict()
        self.gatesets = _collections.OrderedDict()
        self.confidence_regions = _collections.OrderedDict()

        #Set gatesets
        if targetGateset: self.gatesets['target'] = targetGateset
        if seedGateset: self.gatesets['seed'] = seedGateset
        if gatesetsByIter:
            self.gatesets['iteration estimates'] = gatesetsByIter
            self.gatesets['final iteration estimate'] = gatesetsByIter[-1]

        #Set parameters
        if isinstance(parameters, _collections.OrderedDict):
            self.parameters = parameters
        elif parameters is not None:
            for key in sorted(list(parameters.keys())):
                self.parameters[key] = parameters[key]

                
    def add_gaugeoptimized(self, goparams, gateset=None, label=None):
        """
        Adds a gauge-optimized GateSet (computing it if needed) to this object.

        Parameters
        ----------
        goparams : dict
            A dictionary of gauge-optimization parameters, typically arguments
            to :func:`gaugeopt_to_target`, specifying how the gauge optimization
            was (or should be) performed.  When `gateset` is `None` (and this
            function computes the gate set internally) the keys and values of
            this dictionary must correspond to allowed arguments of 
            :func:`gaugeopt_to_target`. By default, :func:`gaugeopt_to_target`'s
            first two arguments, the `GateSet` to optimize and the target,
            are taken to be `self.gatesets['final iteration estimate']` and 
            self.gatesets['target'].

        gateset : GateSet, optional
            The gauge-optimized gate set to store.  If None, then this gate set
            is computed by calling :func:`gaugeopt_to_target` with the contents
            of `goparams` as arguments as described above.

        label : str, optional
            A label for this gauge-optimized gate set, used as the key in
            this object's `gatesets` and `goparameters` member dictionaries.
            If None, then the next available "go<X>", where <X> is a 
            non-negative integer, is used as the label.

        Returns
        -------
        None
        """

        if label is None:
            i = 0
            while True:
                label = "go%d" % i; i += 1
                if (label not in self.goparameters) and \
                   (label not in self.gatesets): break

        if gateset is None:
            goparams = goparams.copy() #so we don't change the caller's dict
            
            if "gateset" not in goparams:
                if 'final iteration estimate' in self.gatesets:
                    goparams["gateset"] = self.gatesets['final iteration estimate']
                else: raise ValueError("Must supply 'gateset' in 'goparams' argument")
                
            if "targetGateset" not in goparams:
                if 'target' in self.gatesets:
                    goparams["targetGateset"] = self.gatesets['target']
                else: raise ValueError("Must supply 'targetGateset' in 'goparams' argument")

            goparams['returnAll'] = True
            starting_gateset = goparams["gateset"].copy()
            minF, gaugeGroupEl, gateset = _gaugeopt_to_target(**goparams)
            goparams['_gaugeGroupEl'] = gaugeGroupEl # an output stored here for convenience
            
        #sort the parameters by name for consistency
        ordered_goparams = _collections.OrderedDict( 
            [(k,goparams[k]) for k in sorted(list(goparams.keys()))])

        self.gatesets[label] = gateset
        self.goparameters[label] = ordered_goparams

        
    def propagate_confidence_region(self, label, confidenceLevel=95,
                                    ref_gateset_key = 'final iteration estimate',
                                    EPS=1e-3):
        """
        Propagates an existing "reference" confidence region for some GateSet
        "G0" to a new confidence region for a gauge-equivalent gateset "G1".

        When successful, a new confidence region will be created for the 
        gauge-optimized gate set given by `label` and stored internally, as well
        as returned.

        Parameters
        ----------
        label : str
            The key into this `Estimate` object's `gatesets` and `goparameters`
            dictionaries that identifies a gauge optimization result.  This 
            gauge optimization must have begun at the reference gateset, i.e.,
            `gatesets[ref_gateset_key]` must equal (by frobeinus distance)
            `goparameters[label]['gateset']`.

        confidenceLevel : float, optional
            The confidence level as a percentage (0-100) of the reference
            confidence region being propagated.

        ref_gateset_key : str, optional
            The key within `gatesets` of the reference gate set.

        EPS : float, optional
            A small offset used for constructing finite-difference derivatives.
            Usually the default value is fine.

        Returns
        -------
        ConfidenceRegion
            Note: this region is also stored internally and as such the return
            value of this function can often be ignored.
        """
        ref_gateset = self.gatesets[ref_gateset_key]
        goparams = self.goparameters[label]
        start_gateset = goparams['gateset'].copy()
        final_gateset = self.gatesets[label].copy()

        assert('_gaugeGroupEl' in goparams),"To propagate a confidence " + \
            "region, goparameters must contain the gauge-group-element as `_gaugeGroupEl`"
        gaugeGroupEl = goparams['_gaugeGroupEl']

        assert(start_gateset.frobeniusdist(ref_gateset) < 1e-6), \
            "Gauge-opt starting point must be the reference GateSet"
        
        cr = self.confidence_regions.get(
            self._crkey(ref_gateset_key, 'final', confidenceLevel), None)
            #TODO: let string list key ('final' above) be variable?
            
        assert(cr is not None), "Reference confidence region doesn't exist!"
        assert(cr.hessianProjection != "linear response"), \
            "Reference confidence region must be Hessian-based!"
                            
        #Update hessian by TMx = d(diffs in current go'd gateset)/d(diffs in ref gateset)
        TMx = _np.empty( (final_gateset.num_params(), ref_gateset.num_params()), 'd' )
        v0, w0 = ref_gateset.to_vector(), final_gateset.to_vector()
        gs = ref_gateset.copy()
        for iCol in range(ref_gateset.num_params()):
            v = v0.copy(); v[iCol] += EPS # dv is along iCol-th direction 
            gs.from_vector(v)
            gs.transform(gaugeGroupEl)
            w = gs.to_vector()
            dw = (w - w0)/EPS
            if iCol % 10 == 0: print("DB: col %d/%d: %g" % (iCol, ref_gateset.num_params(),_np.linalg.norm(dw)))
            TMx[:,iCol] = dw

        rank = _np.linalg.matrix_rank(TMx)
        print("DEBUG: constructed TMx: rank = ", rank)
        
        # Hessian is gauge-transported via H -> TMx_inv^T * H * TMx_inv
        TMx_inv = _np.linalg.inv(TMx)
        new_hessian = _np.dot(TMx_inv.T, _np.dot(cr.hessian, TMx_inv))

        #Create a new confidence region based on the new hessian
        new_cr = _objs.ConfidenceRegion(final_gateset, new_hessian, confidenceLevel,
                                        cr.hessianProjection,
                                        nonMarkRadiusSq=cr.nonMarkRadiusSq)
        new_crKey = self._crkey(label, 'final', confidenceLevel)
        self.confidence_regions[new_crKey] = new_cr
        print("DEBUG: Done transporting CI.  Success!")

        return new_cr

        
    def _crkey(self, gateset_key, gatestrings_key, confidenceLevel):
        return gateset_key + "." + gatestrings_key \
            + "." + str(confidenceLevel)
        
    def get_confidence_region(self, confidenceLevel=95,
                              gateset_key="final iteration estimate",
                              gatestrings_key="final", 
                              label=None, forcecreate=False,
                              allowcreate=True, comm=None):
        """
        Get the ConfidenceRegion object associated with a given gate set and
        confidence level.

        If such a region already exists within this Estimate object's 
        `confidence_regions` dictionary (dictated by `label`) then it will be
        returned instead of creating a region (unless `forcecreate == True`).
        If a new region is constructed it will automatically be added to this
        object's `confidence_regions` dictionary with the key `label`.  If
        such a region doesn't exist and `allowcreate == False` None is returned.

        This function is essentailly a wrapper which maps values from the
        `parameters` dictionary of this object to the arguments of 
        :func:`logl_confidence_region` or :func:`chi2_confidence_region`
        based on the value of `parameters['objective']`.  Namely, the values of
        'objective', 'probClipInterval', 'minProbClip', 'minProbClipForWeighting',
        'radius', 'hessianProjection', 'memlimit', 'cptpPentaltyFactor', and 
        'distributeMethod' are used. If you find yourself having to set values
        in the `parameters` dictionary *just* to call this function, you should
        probably be calling one of the aforementioned functions directly instead
        of this one.

        Parameters
        ----------
        confidenceLevel : int, optional
            The confidence level (between 0 and 100) for normal confidence
            regions or a *negative* integer (between -1 and -100) for 
            "non-Markovian error bar" regions.

        gateset_key : str, optional
            The key in `self.gatesets` of the `GateSet` to retrieve or create
            a `ConfidenceRegion` for.

        gatestrings_key : str, optional
            The key in parent `Result` object's `gatestring_structs` (attempted
            first) or `gatestring_lists` (attempted second) member specifying
            the list of gatestrings to create create a `ConfidenceRegion` for.

        label : str, optional
            The label to give this confidence region.  If None, then
            `gateset_key + "." + gatestrings_key + "." + str(confidenceLevel)`
            is taken to be the label.

        forcecreate : bool, optional
            If True, then a new region will always be created, even if one
            already exists.

        allowcreate : bool, optional
            If True, a new region will be created if one doesn't exist.  If
            False, `None` will be returned when a region doesn't already exist.

        comm : mpi4py.MPI.Comm, optional
            When not None, an MPI communicator for distributing the computation
            across multiple processors.

        Returns
        -------
        ConfidenceRegion or None
            returns None if `confidenceLevel` is None.
        """

        if confidenceLevel is None:
            return None

        crkey = label if (label is not None) else \
                self._crkey(gateset_key, gatestrings_key, confidenceLevel)

        assert( not (forcecreate and not allowcreate)), \
            "Cannot set `forcecreate=True` with `allowcreate=False`"
        
        if (not allowcreate) and (crkey not in self.confidence_regions):
            return None
        
        if forcecreate or (crkey not in self.confidence_regions):
            
            gateset = self.gatesets[gateset_key]
            p = self.parent
            if gatestrings_key in p.gatestring_structs:
                gatestrings = p.gatestring_structs[gatestrings_key].allstrs
                aliases = p.gatestring_structs[gatestrings_key].aliases
            elif gatestrings_key in p.gatestring_lists:
                gatestrings = p.gatestring_lists[gatestrings_key]
                aliases = None
            else: raise ValueError("key '%s' not found in " % gatestrings_key +
                                   "gatestring_structs or gatestring_lists")

            #Negative confidence levels ==> non-Markovian error bars
            if confidenceLevel < 0:
                actual_confidenceLevel = -confidenceLevel
                regionType = "non-markovian"
            else:
                actual_confidenceLevel = confidenceLevel
                regionType = "std"

            ds = self.get_effective_dataset()

            #Check for long hessian computation on a single proc
            if comm is None and gateset.dim > 4 and len(gatestrings) > 100:
                _warnings.warn(("Confidence region computations for systems"
                                " larger than 1 qubit on a single processor"
                                " may take a long time (many hours).  You might"
                                " not want to do this, so I'm going to sleep for"
                                " 10s to give you a chance to kill me before"
                                " I start intensive computation."))
                _time.sleep(10)
            
            params = self.parameters
            objective = params.get('objective',"logl")
            if objective == "logl":
                cr = _const.logl_confidence_region(
                    gateset, ds, actual_confidenceLevel, gatestrings,
                    params.get('probClipInterval',(-1e6,1e6)),
                    params.get('minProbClip',1e-4),
                    params.get('radius',1e-4),
                    params.get('hessianProjection','optimal gate CIs'),
                    regionType, comm, params.get('memLimit',None),
                    params.get('cptpPenaltyFactor',0.0),
                    params.get('distributeMethod','deriv'),
                    aliases)
            elif objective == "chi2":
                cr = _const.chi2_confidence_region(
                    gateset, ds, actual_confidenceLevel, gatestrings,
                    params.get('probClipInterval',(-1e6,1e6)),
                    params.get('minProbClipForWeighting',1e-4),
                    params.get('hessianProjection','optimal gate CIs'),
                    regionType, comm, params.get('memLimit',None),
                    aliases)
            else:
                raise ValueError("Invalid objective given in essential" +
                                 " info: %s" % objective)

            self.confidence_regions[crkey] = cr
            
        return self.confidence_regions[crkey]


    def get_effective_dataset(self, return_subMxs=False):
        """
        Generate a `DataSet` containing the effective counts as dictated by
        the "weights" parameter, which specifies a dict of gate string weights.

        This function rescales the actual data contained in this Estimate's
        parent `Results` object according to the estimate's "weights" parameter.
        The scaled data set is returned, along with (optionall) a list-of-lists
        of matrices containing the scaling values which can be easily plotted
        via a `ColorBoxPlot`.

        Parameters
        ----------
        return_subMxs : boolean
            If true, also return a list-of-lists of matrices containing the
            scaling values, as described above.

        Returns
        -------
        ds : DataSet
            The "effective" (scaled) data set.

        subMxs : list-of-lists
            Only returned if `return_subMxs == True`.  Contains the
            scale values (see above).
        """
        p = self.parent
        gss = p.gatestring_structs['final'] #FUTURE: overrideable?
        weights = self.parameters.get("weights",None)
        
        if weights is not None:
            #TODO: REMOVE
            #obj = params.get('objective',None)
            #assert(obj in ('chi2','logl')),"Invalid objective!"
            #fitFn = _ph.chi2_matrix if obj == "chi2" else _ph.logl_matrix
            #            
            #gss = p.gatestring_structs['final'] #FUTURE: overrideable?
            #probs_precomp_dict = _ph._computeProbabilities(gss, gss, p.dataset)
            #expected = (len(p.dataset.get_spam_labels())-1) # == "k"
            #dof_per_box = 1; nboxes = len(gss.allstrs)                               
            #threshold = _np.ceil(_chi2.ppf(1 - pc/nboxes, dof_per_box))

            scaled_dataset = p.dataset.copy_nonstatic()

            subMxs = []
            for y in gss.used_yvals():
                subMxs.append( [] )
                for x in gss.used_xvals():
                    plaq = gss.get_plaquette(x,y).expand_aliases()
                    scalingMx = _np.nan * _np.ones( (plaq.rows,plaq.cols), 'd')
                    
                    for i,j,gstr in plaq:
                        scalingMx[i,j] = weights.get(gstr,1.0)
                        if scalingMx[i,j] != 1.0:
                            scaled_dataset[gstr].scale(scalingMx[i,j])

                    #build up a subMxs list-of-lists as a plotting
                    # function does, so we can easily plot the scaling
                    # factors in a color box plot.
                    subMxs[-1].append(scalingMx)

            scaled_dataset.done_adding_data()
            if return_subMxs:
                return scaled_dataset, subMxs
            else: return scaled_dataset
            
        else: #no weights specified - just return original dataset (no scaling)
            
            if return_subMxs: #then need to create subMxs with all 1's
                subMxs = []
                for y in gss.used_yvals():
                    subMxs.append( [] )
                    for x in gss.used_xvals():
                        plaq = gss.get_plaquette(x,y)
                        scalingMx = _np.nan * _np.ones( (plaq.rows,plaq.cols), 'd')
                        for i,j,gstr in plaq:
                            scalingMx[i,j] = 1.0
                        subMxs[-1].append( scalingMx )
                return p.dataset, subMxs #copy dataset?
            else:
                return p.dataset

    def misfit_sigma(self):
        """
        Returns the number of standard deviations (sigma) of model violation.

        Returns
        -------
        float
        """
        p = self.parent
        obj = self.parameters.get('objective',None)
        assert(obj in ('chi2','logl')),"Invalid objective!"

        gs = self.gatesets['final iteration estimate'] #FUTURE: overrideable?
        gss = p.gatestring_structs['final'] #FUTURE: overrideable?
        mpc = self.parameters.get('minProbClipForWeighting',1e-4)
        ds = self.get_effective_dataset()
        
        if obj == "chi2":
            fitQty = _tools.chi2( ds, gs, gss.allstrs,
                                  minProbClipForWeighting=mpc,
                                  gateLabelAliases=gss.aliases)
        elif obj == "logl":
            logL_upperbound = _tools.logl_max(ds, gss.allstrs, gateLabelAliases=gss.aliases)
            logl = _tools.logl( gs, ds, gss.allstrs, gateLabelAliases=gss.aliases)
            fitQty = 2*(logL_upperbound - logl) # twoDeltaLogL
            
        Ns = len(gss.allstrs)*(len(ds.get_spam_labels())-1) #number of independent parameters in dataset
        Np = gs.num_params() #don't bother with non-gauge only here [FUTURE: add option for this?]
        k = max(Ns-Np,1) #expected chi^2 or 2*(logL_ub-logl) mean
        if Ns <= Np: _warnings.warn("Max-model params (%d) <= gate set params (%d)!  Using k == 1." % (Ns,Np))
        return (fitQty-k)/_np.sqrt(2*k)



    def copy(self):
        """ Creates a copy of this Estimate object. """
        #TODO: check whether this deep copies (if we want it to...) - I expect it doesn't currently
        cpy = Estimate()
        cpy.parameters = self.parameters.copy()
        cpy.goparameters = self.goparameters.copy()
        cpy.gatesets = self.gatesets.copy()
        cpy.confidence_regions = self.confidence_regions.copy()
        return cpy

    def __str__(self):
        s  = "----------------------------------------------------------\n"
        s += "---------------- pyGSTi Estimate Object ------------------\n"
        s += "----------------------------------------------------------\n"
        s += "\n"
        s += "How to access my contents:\n\n"
        s += " .gatesets   -- a dictionary of GateSet objects w/keys:\n"
        s += " ---------------------------------------------------------\n"
        s += "  " + "\n  ".join(list(self.gatesets.keys())) + "\n"
        s += "\n"        
        s += " .parameters   -- a dictionary of simulation parameters:\n"
        s += " ---------------------------------------------------------\n"
        s += "  " + "\n  ".join(list(self.parameters.keys())) + "\n"
        s += "\n"
        s += " .goparameters   -- a dictionary of gauge-optimization parameter dictionaries:\n"
        s += " ---------------------------------------------------------\n"
        s += "  " + "\n  ".join(list(self.goparameters.keys())) + "\n"
        s += "\n"
        return s
    
    def __getstate__(self):
        # don't pickle parent (will create circular reference)
        to_pickle = self.__dict__.copy()
        del to_pickle['parent'] 
        return  to_pickle

    def __setstate__(self, stateDict):
        self.__dict__.update(stateDict)
        self.parent = None # initialize to None upon unpickling

    def set_parent(self, parent):
        """
        Sets the parent Results object of this Estimate.
        """
        self.parent = parent
        

        

class Results(object):
    """
    Encapsulates a set of related GST estimates.

    A Results object is a container which associates a single `DataSet` and a
    structured set of gate sequences (usually the experiments contained in the
    data set) with a set of estimates.  Each estimate (`Estimate` object) contains
    gate sets as well as parameters used to generate those inputs.  Associated
    `ConfidenceRegion` objects, because they are associated with a set of gate
    sequences, are held in the `Results` object but are associated with estimates.

    Typically, each `Estimate` is related to the input & output of a single
    GST calculation performed by a high-level driver routine like
    :func:`do_long_sequence_gst`.
    """

    def __init__(self):
        """
        Initialize an empty Results object.
        """

        #Dictionaries of inputs & outputs
        self.dataset = None
        self.gatestring_lists = _collections.OrderedDict()
        self.gatestring_structs = _collections.OrderedDict()
        self.estimates = _collections.OrderedDict()


    def init_dataset(self, dataset):
        """
        Initialize the (single) dataset of this `Results` object.

        Parameters
        ----------
        dataset : DataSet
            The dataset used to construct the estimates found in this
            `Results` object.

        Returns
        -------
        None
        """
        if self.dataset is not None:
            _warnings.warn(("Re-initializing the dataset of a Results object!"
                            "  Usually you don't want to do this."))
        self.dataset = dataset

        
    def init_gatestrings(self, structsByIter):
        """
        Initialize the common set gate sequences used to form the 
        estimates of this Results object.

        There is one such set per GST iteration (if a non-iterative
        GST method was used, this is treated as a single iteration).

        Parameters
        ----------
        structsByIter : list
            The gate strings used at each iteration. Ideally, elements are
            `LsGermsStruct` objects, which contain the structure needed to 
            create color box plots in reports.  Elements may also be 
            unstructured lists of gate sequences (but this may limit
            the amount of data visualization one can perform later).

        Returns
        -------
        None
        """
        if len(self.gatestring_structs) > 0:
            _warnings.warn(("Re-initializing the gate sequences of a Results"
                            " object!  Usually you don't want to do this."))
        
        #Set gatestring structures
        self.gatestring_structs['iteration'] = []
        for gss in structsByIter:
            if isinstance(gss, _objs.LsGermsStructure):
                self.gatestring_structs['iteration'].append(gss)
            elif isinstance(gss, list):
                unindexed_gss = _objs.LsGermsStructure([],[],[],[],None)
                unindexed_gss.add_unindexed(gss)
                self.gatestring_structs['iteration'].append(unindexed_gss)
            else:
                raise ValueError("Unknown type of gate string specifier: %s"
                                 % str(type(gss)))
                
        self.gatestring_structs['final'] = \
                self.gatestring_structs['iteration'][-1]

        #Extract raw gatestring lists from structs
        self.gatestring_lists['iteration'] = \
                [ gss.allstrs for gss in self.gatestring_structs['iteration'] ]
        self.gatestring_lists['final'] = self.gatestring_lists['iteration'][-1]
        self.gatestring_lists['all'] = _lt.remove_duplicates(
            list(_itertools.chain(*self.gatestring_lists['iteration'])) )
        
        running_lst = []; delta_lsts = []
        for lst in self.gatestring_lists['iteration']:
            delta_lst = [ x for x in lst if (x not in running_lst) ]
            delta_lsts.append(delta_lst); running_lst.extend(delta_lst) 
        self.gatestring_lists['iteration delta'] = delta_lsts # *added* at each iteration

        #Set "Ls and germs" info: gives particular structure
        # to the gateStringLists used to obtain estimates
        finalStruct = self.gatestring_structs['final']
        self.gatestring_lists['prep fiducials'] = finalStruct.prepStrs
        self.gatestring_lists['effect fiducials'] = finalStruct.effectStrs
        self.gatestring_lists['germs'] = finalStruct.germs


    def add_estimates(self, results, estimatesToAdd=None):
        """
        Add some or all of the estimates from `results` to this `Results` object.

        Parameters
        ----------
        results : Results
            The object to import estimates from.  Note that this object must contain
            the same data set and gate sequence information as the importing object
            or an error is raised.

        estimatesToAdd : list, optional
            A list of estimate keys to import from `results`.  If None, then all
            the estimates contained in `results` are imported.

        Returns
        -------
        None
        """
        if self.dataset is None:
            raise ValueError(("The data set must be initialized"
                              "*before* adding estimates"))

        if 'iteration' not in self.gatestring_structs:
            raise ValueError(("Gate sequences must be initialized"
                              "*before* adding estimates"))

        assert(results.dataset is self.dataset), "DataSet inconsistency: cannot import estimates!"
        assert(len(self.gatestring_structs['iteration']) == len(results.gatestring_structs['iteration'])), \
            "Iteration count inconsistency: cannot import estimates!"

        for estimate_key in results.estimates:
            if estimatesToAdd is None or estimate_key in estimatesToAdd:
                if estimate_key in self.estimates:
                    _warnings.warn("Re-initializing the %s estimate" % estimate_key
                                   + " of this Results object!  Usually you don't"
                                   + " want to do this.")
                self.estimates[estimate_key] = results.estimates[estimate_key]

        
    def add_estimate(self, targetGateset, seedGateset, gatesetsByIter,
                     parameters, estimate_key='default'):
        """
        Add a set of `GateSet` estimates to this `Results` object.

        Parameters
        ----------
        targetGateset : GateSet
            The target gateset used when optimizing the objective.

        seedGateset : GateSet
            The initial gateset used to seed the iterative part
            of the objective optimization.  Typically this is
            obtained via LGST.

        gatesetsByIter : list of GateSets
            The estimated gateset at each GST iteration. Typically these are the
            estimated gate sets *before* any gauge optimization is performed.

        parameters : dict
            A dictionary of parameters associated with how this estimate
            was obtained.

        estimate_key : str, optional
            The key or label used to identify this estimate.

        Returns
        -------
        None
        """
        if self.dataset is None:
            raise ValueError(("The data set must be initialized"
                              "*before* adding estimates"))

        if 'iteration' not in self.gatestring_structs:
            raise ValueError(("Gate sequences must be initialized"
                              "*before* adding estimates"))

        assert(len(self.gatestring_structs['iteration']) == len(gatesetsByIter))

        if estimate_key in self.estimates:
            _warnings.warn("Re-initializing the %s estimate" % estimate_key
                           + " of this Results object!  Usually you don't"
                           + " want to do this.")

        self.estimates[estimate_key] = Estimate(self, targetGateset, seedGateset,
                                                gatesetsByIter, parameters)

        #Set gate sequence related parameters inherited from Results
        self.estimates[estimate_key].parameters['max length list'] = \
                                        self.gatestring_structs['final'].Ls


    def copy(self):
        """ Creates a copy of this Results object. """
        #TODO: check whether this deep copies (if we want it to...) - I expect it doesn't currently
        cpy = Results()
        cpy.dataset = self.dataset.copy()
        cpy.gatestring_lists = self.gatestring_lists.copy()
        cpy.gatestring_structs = self.gatestring_structs.copy()
        cpy.estimates = self.estimates.copy()
        return cpy


    def __setstate__(self, stateDict):
        if '_bEssentialResultsSet' in stateDict:
            #Then we're unpickling an old-version Results object
            print("NOTE: you're loading a prior-version Results object from a pickle."
                  " This Results object will been updated, and while most data will"
                  " be transferred seamlessly, there may be some saved values which"
                  " are not imported. Please re-save (or re-pickle) this upgraded object"
                  " to avoid seeing this message, or re-run the analysis leading to "
                  " these results to create a new current-version Results object.")
            
            params = _collections.OrderedDict()
            goparams = _collections.OrderedDict()
            for k,v in stateDict['parameters'].items():
                if k != 'gaugeOptParams': params[k] = v
                elif isinstance(v,list) and len(v) == 1:
                    goparams['go0'] = v[0]
                else:
                    goparams['go0'] = v

            gstrStructs = _collections.OrderedDict()
            if _SHORTCUT_OLD_RESULTS_LOAD == False:
                try:
                    prepStrs = stateDict['gatestring_lists']['prep fiducials']
                    effectStrs = stateDict['gatestring_lists']['effect fiducials']
                    germs = stateDict['gatestring_lists']['germs']
                    aliases = stateDict['parameters'].get('gateLabelAliases',None)
                    fidPairs = stateDict['parameters'].get('fiducial pairs',None)
                    maxLengthList = stateDict['parameters']['max length list']
                    if maxLengthList[0] == 0:
                        maxLengthList = maxLengthList[1:] #Fine; includeLGST is always True below
                
                    structs = _const.make_lsgst_structs(stateDict['gatesets']['target'].gates.keys(),
                                                        prepStrs, effectStrs, germs, maxLengthList,
                                                        fidPairs, truncScheme="whole germ powers",
                                                        nest=True, keepFraction=1, keepSeed=None,
                                                        includeLGST=True, gateLabelAliases=aliases)
                except:
                    print("Warning: Ls & germs structure not found.  Loading unstructured Results.")
                    structs = []
                    for lst in stateDict['gatestring_lists']['iteration']:
                        unindexed_gss = _objs.LsGermsStructure([],[],[],[],None)
                        unindexed_gss.add_unindexed(lst)
                        structs.append(unindexed_gss)
                        
                gstrStructs['iteration'] = structs
                gstrStructs['final'] = structs[-1]

            gstrLists = _collections.OrderedDict()
            for k,v in stateDict['gatestring_lists'].items():
                gstrLists[k] = v

            gatesets =  _collections.OrderedDict()
            for k,v in stateDict['gatesets'].items():
                if k == 'final estimate':
                    gatesets['go0'] = v
                elif k == 'iteration estimates pre gauge opt':
                    gatesets['iteration estimates'] = v
                else: gatesets[k] = v
            gatesets['final iteration estimate'] = gatesets['iteration estimates'][-1]

            estimate = Estimate(self, gatesets['target'], gatesets['seed'],
                                gatesets['iteration estimates'], params)
            if 'go0' in gatesets:
                estimate.add_gaugeoptimized(goparams.get('go0',{}), gatesets['go0'])
                
            filteredDict = {
                'dataset': stateDict['dataset'],
                'gatestring_lists': gstrLists,
                'gatestring_structs': gstrStructs,
                'estimates': _collections.OrderedDict( [('default',estimate)] ),
            }
            self.__dict__.update(filteredDict)
        else:
            #unpickle normally
            self.__dict__.update(stateDict)
            for est in self.estimates.values():
                est.set_parent(self)
                

    def __str__(self):
        s  = "----------------------------------------------------------\n"
        s += "---------------- pyGSTi Results Object -------------------\n"
        s += "----------------------------------------------------------\n"
        s += "\n"
        s += "How to access my contents:\n\n"
        s += " .dataset    -- the DataSet used to generate these results\n\n"
        s += " .gatestring_lists   -- a dict of GateString lists w/keys:\n"
        s += " ---------------------------------------------------------\n"
        s += "  " + "\n  ".join(list(self.gatestring_lists.keys())) + "\n"
        s += "\n"
        s += " .gatestring_structs   -- a dict of GatestringStructures w/keys:\n"
        s += " ---------------------------------------------------------\n"
        s += "  " + "\n  ".join(list(self.gatestring_structs.keys())) + "\n"
        s += "\n"
        s += " .estimates   -- a dictionary of Estimate objects:\n"
        s += " ---------------------------------------------------------\n"
        s += "  " + "\n  ".join(list(self.estimates.keys())) + "\n"
        s += "\n"
        return s


    #OLD Methods for generating reports which have been removed - show alert
    # message directing users to new factory functions
    def create_full_report_pdf(self, confidenceLevel=None, filename="auto",
                               title="auto", datasetLabel="auto", suffix="",
                               debugAidsAppendix=False, gaugeOptAppendix=False,
                               pixelPlotAppendix=False, whackamoleAppendix=False,
                               pureDataAppendix=False,  m=0, M=10, tips=False,
                               verbosity=0, comm=None):
        _warnings.warn(
            ('create_full_report_pdf(...) has been removed from pyGSTi.\n'
             '  Starting in version 0.9.4, pyGSTi\'s PDF reports have been\n'
             '  replaced with (better) HTML ones. As a part of this change,\n'
             '  the functions that generate reports are now separate functions.\n'
             '  Please update this call with one to:\n'
             '  pygsti.report.create_general_report(...)\n'))

    def create_brief_report_pdf(self, confidenceLevel=None,
                                filename="auto", title="auto", datasetLabel="auto",
                                suffix="", m=0, M=10, tips=False, verbosity=0,
                                comm=None):
        _warnings.warn(
            ('create_brief_report_pdf(...) has been removed from pyGSTi.\n'
             '  Starting in version 0.9.4, pyGSTi\'s PDF reports have been\n'
             '  replaced with (better) HTML ones. As a part of this change,\n'
             '  the functions that generate reports are now separate functions.\n'
             '  Please update this call with one to:\n'
             '  pygsti.report.create_general_report(...)\n'))

    def create_presentation_pdf(self, confidenceLevel=None, filename="auto",
                                title="auto", datasetLabel="auto", suffix="",
                                debugAidsAppendix=False,
                                pixelPlotAppendix=False, whackamoleAppendix=False,
                                m=0, M=10, verbosity=0, comm=None):
        _warnings.warn(
            ('create_presentation_pdf(...) has been removed from pyGSTi.\n'
             '  Starting in version 0.9.4, pyGSTi\'s PDF reports have been\n'
             '  replaced with (better) HTML ones. As a part of this change,\n'
             '  Beamer presentations have been removed.  Please try using\n'
             '  pygsti.report.create_general_report(...)\n'))

    def create_presentation_ppt(self, confidenceLevel=None, filename="auto",
                            title="auto", datasetLabel="auto", suffix="",
                            debugAidsAppendix=False,
                            pixelPlotAppendix=False, whackamoleAppendix=False,
                            m=0, M=10, verbosity=0, pptTables=False, comm=None):
        _warnings.warn(
            ('create_presentation_ppt(...) has been removed from pyGSTi.\n'
             '  Starting in version 0.9.4, pyGSTi\'s PDF reports have been\n'
             '  replaced with (better) HTML ones. As a part of this change,\n'
             '  Powerpoint presentations have been removed.  Please try using\n'
             '  pygsti.report.create_general_report(...)\n'))

    def create_general_report_pdf(self, confidenceLevel=None, filename="auto",
                                  title="auto", datasetLabel="auto", suffix="",
                                  tips=False, verbosity=0, comm=None,
                                  showAppendix=False):
        _warnings.warn(
            ('create_general_report_pdf(...) has been removed from pyGSTi.\n'
             '  Starting in version 0.9.4, pyGSTi\'s PDF reports have been\n'
             '  replaced with (better) HTML ones. As a part of this change,\n'
             '  the functions that generate reports are now separate functions.\n'
             '  Please update this call with one to:\n'
             '  pygsti.report.create_general_report(...)\n'))

class ResultOptions(object):
    """ Unused.  Exists for sole purpose of loading old Results pickles """
    pass

#Define empty ResultCache class in resultcache module to enable loading old Results pickles
import sys as _sys
class dummy_ResultCache(object): pass
class dummy_resultcache_module(object):
    def __init__(self):
        self.ResultCache = dummy_ResultCache
_sys.modules['pygsti.report.resultcache'] = dummy_resultcache_module()
