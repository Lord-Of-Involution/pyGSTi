""" Defines the Circuit class """
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************

import numbers as _numbers
import numpy as _np
import copy as _copy

from . import gatestring as _gstr
from ..baseobjs import Label as _Label

class Circuit(_gstr.GateString):
    """
    A Circuit is a more structured representation of a sequence of preparation,
    gate, and measurement operations.  It is composed of some number of "lines",
    typically one per qubit, and permits a richer set of operations than 
    :class:`GateString`.  These operations include a range of methods for
    manipulating quantum circuits. E.g., basic depth compression algorithms.
    """   
    def __init__(self, line_items=None, gatestring=None, num_lines=None,
                 line_labels=None, parallelize=False, identity='I'):
        """
        Creates a new Circuit object, encapsulating a quantum circuit.

        You can supply at most one of `line_items` and `gatestring` (alternate
        ways of specifying the gates).  If neither are specified an empty
        Circuit is created.  Unless `line_items` is specified, you must also
        specify the number of lines via `num_lines` and/or `line_labels`. If
         labels aren't specified they default to the integers starting at 0.

        Parameters
        ----------
        line_items : list, optional
            A list of lists of Label objects, giving the gate labels present on
            each "line" (usually "qubit") of the circuit.  When a gate occupies
            more than one line its label is present in the lists of *all* the
            lines it occupies.

        gatestring : list, optional
            A list of Label objects, specifying a serial sequence of gates to
            be made into a circuit.  Gates are placed in as few "layers" as 
            possible, meaning that gates acting on different qubits are 
            done in parallel (placed at the same position in their respective
            lines).  This is equivalent to saying the list for each line is 
            made as short as possible.

        num_lines : int, optional
            The number of lines (usually qubits).  You only need to specify 
            this when it cannot be inferred, that is, when `line_items` or
            `line_labels` is not given.

        line_labels : list, optional
            A list of strings or integers labelling each of the lines.  The
            length of this list equals the number of lines in the circuit, 
            and if `line_labels` is not given these labels default to the 
            integers starting with 0.

        parallelize : bool, optional
            Only used when initializing from `gatestring`.  When True, automatic
            parallelization is performed: consecutive gates in `gatestring`
            acting on disjoint sets of qubits are placed in the same layer.

        identity : str, optional
            The "name" for the identity gate. This is the gate name that will
            be used to "pad" layers: qubits that are without a gate in
            a layer when the circuit is constructed will be assigned an idle gate
            with a name fixed by this string. Unlike all other gates, the created
            circuit "knows" that this particular gate is an idle. So, the circuit
            will potentially drop idle gates when doing depth-compression, whereas 
            all other gates are treat as having an unspecified action, by all methods
            of the circuit, unless the relationship between the gates is given to 
            a method of circuit.        
        """
        assert(type(identity) == str), "The identity name must be a string!"
        self.identity = identity

        assert((line_items is not None) or (gatestring is not None) or (num_lines is not None) or (line_labels is not None)), \
            "At least one of these arguments must be not None!"

        self._static = False

        if (num_lines is not None) and (line_labels is not None):
            assert(num_lines == len(line_labels)), "Inconsistent `num_lines` and `line_labels`!"
                
        if line_items is not None:
            assert(gatestring is None), "Cannot specify both `line_items` and `gatestring`"
            self.line_items = line_items
            self.number_of_lines = len(self.line_items)
            if num_lines is not None:
                assert(num_lines == self.number_of_lines), "Inconsistent `line_items` and `num_lines` arguments!"
            if line_labels is not None:
                assert(len(line_labels) == self.number_of_lines), "Inconsistent `line_items` and `line_labels` arguments!"
                self.line_labels = line_labels
            else:
                self.line_labels = list(range(self.number_of_lines))

        else:
            assert(num_lines is not None or line_labels is not None), \
                "`num_lines` or `line_labels`  must be specified whenever `line_items` is None!"
            if num_lines is not None:
                assert(isinstance(num_lines, _numbers.Integral)), "`num_lines` must be an integer!"
                self.number_of_lines = num_lines
            if line_labels is not None:
                self.line_labels = line_labels
                self.number_of_lines = len(line_labels)
            else:
                self.line_labels = list(range(self.number_of_lines))
            
            if gatestring is not None:
                self._initialize_from_gatestring(gatestring, parallelize)
            else:
                self.clear() # initializes an empty circuit

        """ Initialize the members of the GateString base class """
        tup = self._flatten_to_tup()
        strRep = None  #don't worry about string representation currently - just auto-compute it.
        super(Circuit, self).__init__(tup, strRep)

        self._tup_dirty = False # keep track of when we need to _flatten_to_tup
        self._str_dirty = True # keep track of when we need to auto-compute string rep

        # todo : implement this.
        #self.barriers = _np.zeros(self.depth()+1,bool)

    def _reinit_base(self):
        """ Re-initialize the members of the base GateString object """
        if self._tup_dirty:
            self._tup = self._flatten_to_tup()
            self._tup_dirty = False
        if self._str_dirty:
            self._str = _gstr._gateSeqToStr(self._tup)
            self._str_dirty = False
        
    def _flatten_to_tup(self):
        """ Flatten self.line_items into a serial tuple of gate labels """
        #print("DB: flattening to tuple!!")
        if self.number_of_lines <= 0:
            return ()

        label_list = []
        nlayers = max( [len(line) for line in self.line_items] )
        
        #Add gates
        for j in range(nlayers): # j = layer index
            layer_list = []
            processed_lines = set()
            for line_lbl,line in zip(self.line_labels, self.line_items):
                if line_lbl in processed_lines: continue # we've already added the gate/item on this line (e.g. 2Q gates)
                if len(line) <= j: continue # this line doesn't have a j-th layer (is this possible?)

                lbl = line[j]
                if line[j].name != self.identity: #Note: it's OK to use .name on line items (all are *simple* labels)
                    layer_list.append( line[j] ) # don't include exact identities
                actson = lbl.qubits if (lbl.qubits is not None) else self.line_labels # None == "all lines"
                processed_lines.update(actson)

            if len(layer_list) > 0:
                label_list.append( _Label(layer_list) )
                
        return tuple(label_list)

    @property
    def tup(self):
        """ This Circuit as a standard Python tuple of Labels."""
        # Note: this overrides GateString method so we can compute tuple in on-demand way
        #print("Circuit.tup accessed")
        self._reinit_base()
        return self._tup

    @tup.setter
    def tup(self, value):
        """ This Circuit as a standard Python tuple of Labels."""
        #print("Circuit.tup setter accessed")
        self._reinit_base()
        self._tup = value

    @property
    def str(self):
        """ The Python string representation of this GateString."""
        #print("Circuit.str accessed")
        self._reinit_base()
        return self._str

    @str.setter
    def str(self, value):
        """ The Python string representation of this GateString."""
        #print("Circuit.str setter accessed")
        self._reinit_base()
        self._str = value

    def __hash__(self):
        if self._static:
            _warnings.warning(("Editable circuit is being converted to read-only"
                               " mode in order to hash it.  You should call"
                               " circuit.done_editing() beforehand."))
            self.done_editing()
        return super(Circuit,self).__hash__()
                     
    def clear(self):
        """
        Removes all the gates in a circuit (preserving the number of lines).
        """
        assert(not self._static),"Cannot edit a read-only circuit!"
        self.line_items = []
        for i in range(0,self.number_of_lines):
            self.line_items.append([])
        self._tup_dirty = self._str_dirty = True
                        
    def _initialize_from_gatestring(self,gatestring,parallelize):
        """
        Initializes self.line_items from a sequence of Label objects.
        
        Parameters
        ----------
        gatestring : GateString or tuple
            A sequence of state preparation (optional), gates, and measurement
            (optional), given by a :class:`GateString` object.

        parallelize : bool
            Whether or not automatic parallelization should be performed, where
            subsequent gates in `gatestring` acting on disjoint sets of qubits
            should be placed in the same layer.
        """
        assert(not self._static),"Cannot edit a read-only circuit!"
        
        # Get a proper GateString object if one isn't given to us
        if not isinstance(gatestring, _gstr.GateString):
            gatestring = _gstr.GateString(gatestring)

        # Note: elements of gatestring are guaranteed to be Label objs b/c GateString enforces this.
            
        # Create an empty circuit, to populate from gatestring
        self.clear() # inits self.line_items

        # keeps track of which gates have been added to the circuit from the list.
        j = 0
        
        # keeps track of the circuit layer number
        layer_number = 0
        
        while j < len(gatestring):
            layer = [] # The gates that are going into this layer.

            if parallelize:
                k = 0 # The number of gates beyond j that are going into this layer.
                used_qubits = set() # The qubits used in this layer.
                while j+k < len(gatestring):
                    
                    # look at the j+kth gate and include in this layer
                    gate = gatestring[j+k] # really a gate *label*
                    gate_qubits = gate.qubits if (gate.qubits is not None) \
                                  else self.line_labels  # then gate uses *all* lines
    
                    # Checks the qubits are all in the line labels. todo : this doesn't work so fix it!
                    for qubit in gate_qubits:
                        assert(qubit in self.line_labels), "Some gates do not act on the qubits in this circuit!"

                    if len(used_qubits.intersection(gate_qubits)) > 0:
                        break # `gate` can't fit in this layer
                        
                    layer.append(gate)
                    used_qubits.update(gate_qubits)                    
                        
                    # look at the next gate in the list, which will be
                    # added to the layer if it does not act on any qubits
                    # with a gate already in this layer
                    k += 1
            else: # just add the next gate label as the next layer
                k = 1 # The number of gates beyond j that are going into this layer.
                layer.append(gatestring[j])
                
            # Insert the layer into the circuit.
            self.insert_layer(layer,layer_number)
            
            # Move on to the next gate not included in the circuit.
            j += k
            # Update the layer number.
            layer_number += 1
    
    def insert_gate(self,gatelbl,j):
        """
        Inserts a gate into a circuit.
        
        Parameters
        ----------
        gatelbl : Label
            The gate label to insert.
            
        j : int
            The layer index (depth) at which to insert the gate.

        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"       
        # Add an idle layer.
        for i in range(0,self.number_of_lines):
            self.line_items[i].insert(j,_Label(self.identity,self.line_labels[i]))
            
        # Put the gate label in - note this label may
        # be a "parallel-gate" label and have mulitple components.
        for gl_comp in gatelbl.components:
            gate_qubits = gl_comp.qubits if (gl_comp.qubits is not None) \
                          else self.line_labels
            for i in gate_qubits:
                self.line_items[i][j] = gl_comp

        self._tup_dirty = self._str_dirty = True

        
    def insert_layer(self,circuit_layer,j):
        """
        Inserts a layer into a circuit. The input layer does not
        need to contain a gate that acts on every qubit. But,
        it should be a valid layer, meaning that the layer
        does not contain more than one gate on a qubit.
        
        Parameters
        ----------
        circuit_layer : list
            A list of Label objects, to insert as a circuit layer.
            
        j : int
            The layer index (depth) at which to insert the circuit layer.

        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"        
        # Add an idle layer.
        for i in range(0,self.number_of_lines):
            self.line_items[i].insert(j,_Label(self.identity,self.line_labels[i]))
            
        # Put the gates in.
        for i,line_label in enumerate(self.line_labels):
            for gatelbl in circuit_layer:
                # circuit layer can contain "parallel" gate layers, unlike
                # the values of self.line_items which are all simple labels
                for gl_comp in gatelbl.components:
                    gate_qubits = gl_comp.qubits if (gl_comp.qubits is not None) \
                              else self.line_labels
                    if line_label in gate_qubits:
                        self.line_items[i][j] = gl_comp
                    
        self._tup_dirty = self._str_dirty = True
                    
    def insert_circuit(self,circuit,j):
        """
        Inserts a circuit into this circuit.
        
        Parameters
        ----------
        circuit : A Circuit object
            The circuit to be inserted.
            
        j : int
            The layer index (depth) at which to insert the circuit.
            
        Returns
        -------
        None
        """  
        assert(not self._static),"Cannot edit a read-only circuit!"      
        assert(self.number_of_lines == circuit.number_of_lines), "The circuits must act on the same number of qubits!"
        
        for q in range(0,self.number_of_lines):
            self.line_items[q] = self.line_items[q][0:j] + circuit.line_items[q][:] + self.line_items[q][j:]
            
        self._tup_dirty = self._str_dirty = True
                            
    def append_circuit(self,circuit):
        """
        Append a circuit to the end of this circuit.
        
        Parameters
        ----------
        circuit : A Circuit object
            The circuit to be appended.
 
        Returns
        -------
        None
        """   
        assert(not self._static),"Cannot edit a read-only circuit!"     
        assert(self.number_of_lines == circuit.number_of_lines), "The circuits must act on the same number of qubits!"
        
        for q in range(0,self.number_of_lines):
            self.line_items[q] = self.line_items[q] + circuit.line_items[q][:]
        self._tup_dirty = self._str_dirty = True
            
    def prefix_circuit(self,circuit):
        """
        Prefix a circuit to the end of this circuit.
        
        Parameters
        ----------
        circuit : A Circuit object
            The circuit to be prefixed.
 
        Returns
        -------
        None
        """  
        assert(not self._static),"Cannot edit a read-only circuit!"         
        assert(self.number_of_lines == circuit.number_of_lines), "The circuits must act on the same number of qubits!"
        
        for q in range(0,self.number_of_lines):
            self.line_items[q] = circuit.line_items[q][:] + self.line_items[q]
        self._tup_dirty = self._str_dirty = True

        
    def replace_gate_with_circuit(self,circuit,q,j):
        """
        Replace a gate with a circuit. As other gates in the
        layer might not be the idle gate, the circuit is inserted
        so that it starts at layer j+1.
        
        Parameters
        ----------
        circuit : A Circuit object
            The circuit to be inserted in place of the gate.
            
        q : int
            The qubit on which the gate is to be replaced
            
        j : int
            The layer index (depth) of the gate to be replaced.
 
        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"
        n = self.line_items[q][j].number_of_qubits 
        assert(n == 1 or n == 2), "Only circuits with only 1 and 2 qubit gates supported!" 
        
        # Replace the gate with an idle
        if n == 1:
            self.line_items[q][j] = _Label(self.identity,self.line_labels[q])
            
        else:
            q1 = self.line_items[q][j].qubits[0]
            q2 = self.line_items[q][j].qubits[1]
            self.line_items[q1][j] = _Label(self.identity,self.line_labels[int(q1)])
            self.line_items[q2][j] = _Label(self.identity,self.line_labels[int(q2)])
        
        # Insert the circuit
        self.insert_circuit(circuit,j+1)
        
    def replace_layer_with_layer(self,circuit_layer,j):
        """
        Replace a layer with a layer. The input layer does not
        need to contain a gate that acts on every qubit. But,
        it should be a valid layer, meaning that the layer
        does not contain more than one gate on a qubit.
        
        Parameters
        ----------
        circuit_layer : List
            A list of Gate objects, defining a valid layer.
            
        j : int
            The index (depth) of the layer to be replaced.
 
        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"        
        # Replace all gates with idles, in the layer to be replaced.
        for q in range(0,self.number_of_lines):
            self.line_items[q][j] = _Label(self.identity,self.line_labels[q])
        
        # Write in the gates, from the layer to be inserted.
        for q in range(0,self.number_of_lines):
            for gatelbl in circuit_layer:
                for sub_gl in gatelbl.components:
                    if q in sub_gl.qubits:
                        self.line_items[q][j] = sub_gl
        self._tup_dirty = self._str_dirty = True
        
    def replace_layer_with_circuit(self,circuit,j):
        """
        Replace a layer with a circuit.
        
        Parameters
        ----------
        circuit : A Circuit object
            The circuit to be inserted in place of the layer.
  
        j : int
            The index (depth) of the layer to be replaced.
 
        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"
        depth = circuit.depth()
        
        # Replace the layer with the first layer of the input circuit.
        layer = circuit.get_circuit_layer(0)
        self.replace_layer_with_layer(layer,j)
        
        # Insert the other layers of the input circuit.
        for i in range(1,depth):
            layer = circuit.get_circuit_layer(i)
            self.insert_layer(layer,j)
                       
    def replace_gatename(self, old_gatename, new_gatename):
        """
        Changes the *name* of a gate throughout this Circuit.

        Note that the "name" is only a part of the "label" identifying each
        gate, and doesn't include the lines (qubits) a gate acts upon.  For
        example, the "Gx:0" and "Gx:1" labels both have the same name but 
        act on different qubits.

        Another possible use example is the ability to change all of the
        default idle gates (`'I'`), which are added as "padding" during
        circuit construction methods, to something else like `'Gi'`.

        Parameters
        ----------
        old_gatename, new_gatename : string
            The gate name to find and the gate name to replace the found
            name with.

        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"

        depth = self.depth()
        for q in range(self.number_of_lines):
            for l in range(depth):
                if self.line_items[q][l].name == old_gatename:
                    #self.line_items[q][l].name = new_gatename # This doesn't work now for some reason.
                    self.line_items[q][l] = _Label(new_gatename, self.line_items[q][l].qubits)
        self._tup_dirty = self._str_dirty = True
    
    def change_gate_library(self,compilation,depth_compression=True,
                            oneQgate_relations=None):
        """
        Re-express a circuit over a different gateset.
        
        Parameters
        ----------
        compilation : dict
            A dictionary whereby the keys are all of the gates that appear in the circuit, 
            and the values are replacement circuits that are normally compilations for each 
            of these gates (if they are not, the action of the circuit will be changed).
            
        depth_compression : bool, opt
            If True then depth compression is implemented on the output circuit. Without this being 
            set to True, the output circuit will be much larger than necessary, as gates will 
            generically not have been parallelized.
  
        oneQgate_relations : dict, opt
            Gate relations for the one-qubit gates in the new gate library, that are used in the 
            depth compression, to cancel / combine gates. E.g., one key-value pair might be 
            ('H','H') : 'I', to signify that two Hadamards compose to an idle gate.
            
        Returns
        -------
        None
        """ 
        assert(not self._static),"Cannot edit a read-only circuit!"       
        in_compilation = compilation
        
        d = self.depth()
        n = self.number_of_lines
        for l in range(0,d):
            for q in range(0,n):
                gate = self.line_items[q][d-1-l]
                # We ignore idle gates, and do not compile them.
                # To do: is this the behaviour we want?
                if gate.name != self.identity:
                    if gate in in_compilation.keys():
                        self.replace_gate_with_circuit(in_compilation[gate],q,d-1-l)
                    #else:
                    #    # To do: replace with a suitable assert somewhere.
                    #    print('Error: could not find ', gate, ' in ', list(in_compilation.keys()))
        
        # If specified, perform the depth compression.
        if depth_compression:            
            self.compress_depth(oneQgate_relations=oneQgate_relations,verbosity=0)
    
    def map_state_space_labels(self, mapper):
        """
        Return a copy of the circuit with all of the line labels (and the gates) updated according to 
        a mapping function.

        For example, calling this function with `mapper = {0: 1, 1: 3}`
        on the string "Gx:0Gy:1Gx:1" would return "Gx:1Gy:3Gx:3".

        Parameters
        ----------
        mapper : dict or function
            A dictionary whose keys are the existing state-space-label values
            and whose value are the new labels, or a function which takes a
            single (existing label) argument and returns a new label.

        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"
        # If the mapper is a dict, turn it into a function
        if type(mapper) == dict:
            def mapper_func(qlabel):
                return mapper[qlabel]
        else:
            mapper_func = mapper

        self.line_labels = [mapper_func(l) for l in self.line_labels]

        depth = self.depth()
        for i in range(0,self.number_of_lines):
            for j in range(0,depth):
                gate = self.line_items[i][j]
                self.line_items[i][j] = _Label(gate.name,tuple([mapper_func(l) for l in gate.qubits]))

    def reorder_wires(order):
        """
        todo : docstring
        """
        todo : implement

    # Todo : I think we want to delete this function, as it does something quite odd.
    def relabel_qubits(self,order):
        """
        Todo : docstring

            The quantum wire for qubit i becomes
            the quantum wire for qubit order[i]
        """
        assert(not self._static),"Cannot edit a read-only circuit!"
        original_circuit = _copy.deepcopy(self.line_items)
        #for i in range(0,circuit.number_of_qubits):
        #    relabelled_circuit.line_items[order[i]] = circuit.line_items[i]

        depth = self.depth()
        for i in range(0,self.number_of_lines):
            for j in range(0,depth):
                gate = original_circuit[i][j]
                self.line_items[order[i]][j] = _Label(gate.name,tuple([order[k] for k in gate.qubits]))

    def delete_layer(self,j):
        """
        Delete a layer from the circuit.
        
        Parameters
        ----------
        j : int
            The index (depth) of the layer to be deleted.
 
        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"
        for q in range(0,self.number_of_lines):
            del self.line_items[q][j]
        self._tup_dirty = self._str_dirty = True

        
    def get_circuit_layer(self,j):
        """
        Returns the layer at depth j.

        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"       
        assert(j >= 0 and j < self.depth()), "Circuit layer label invalid! Circuit is only of depth {}".format(self.depth())
        
        layer = []
        for i in range(0,self.number_of_lines):
            layer.append(self.line_items[i][j])
            
        return layer
    
    def reverse(self):
        """
        Reverse the order of the circuit.

        Returns
        -------
        None
        """
        assert(not self._static),"Cannot edit a read-only circuit!"         
        for q in range(0,self.number_of_lines):
            self.line_items[q].reverse()
        self._tup_dirty = self._str_dirty = True

        
    def depth(self):
        """
        The circuit depth.
        
        Returns
        -------
        int
        """ 
        return len(self.line_items[0])
    
    def size(self):
        """
        Computes the circuit size, whereby a gate defined as acting on
        n-qubits of size n, with the exception of the special `I` idle 
        gate which is of size 0. Hence, the circuit size is circuit
        depth X number of qubits - number of idle gates in the
        circuit.
        
        Returns
        -------
        int        
        """
        size = 0
        for q in range(0,self.number_of_lines):
            for j in range(0,self.depth()):
                if self.line_items[q][j].name != self.identity:
                    size += 1
        return size
    
    def twoqubit_gatecount(self):
        """
        The number of two-qubit gates in the circuit.
        
        Returns
        -------
        int
        """           
        count = 0
        for q in range(0,self.number_of_lines):
            for j in range(0,self.depth()):
                if self.line_items[q][j].number_of_qubits == 2:
                    count += 1
        return count//2
    
    def predicted_infidelity(self,fidelities):
        
        f = 1.
        # todo: need to check how this behaves with the idle gate.       
        gatestring = self._flatten_to_tup()
        for label in gatestring:
            
            f = f*fidelities[label]
        
        return 1 - f

    def __str__(self):
        """
        A text rendering of the circuit.
        """
        s = ''

        def abbrev(lbl,k): #assumes a simple label w/ name & qubits
            """ Returns what to print on line 'k' for label 'lbl' """
            if lbl.number_of_qubits == 1:
                return lbl.name
            elif lbl.name in ('CNOT','Gcnot'): # qubit indices = (control,target)
                # Tim: display *other* CNOT qubit on each line
                if k == lbl.qubits[0]: return 'C' + str(lbl.qubits[1])
                else:                  return 'T' + str(lbl.qubits[0])          
            else:
                return str(lbl)
        
        max_labellen = [ max([ len(abbrev(self.line_items[i][j],i))
                               for i in range(0,self.number_of_lines)])
                         for j in range(0,self.depth()) ]

        for i in range(0,self.number_of_lines):
            s += 'Qubit {} ---'.format(self.line_labels[i])
            for j,maxlbllen in enumerate(max_labellen):
                if self.line_items[i][j].name == self.identity:
                    # Replace with special idle print at some point
                    #s += '-'*(maxlbllen+3) # 1 for each pipe, 1 for joining dash
                    s += '*'*(maxlbllen+2) + '-' 
                else:
                    lbl = abbrev(self.line_items[i][j],i)
                    pad = maxlbllen - len(lbl)
                    s += '|' + ' '*int(_np.floor(pad/2)) + lbl + ' '*int(_np.ceil(pad/2)) + '|-' #+ '-'*pad
            s += '--\n'

        return s
    
    def write_qcircuit_tex(self,filename):
        """
        Renders this circuit as LaTeX (using Qcircuit).

        Returns
        -------
        str
        """
        n = self.number_of_lines
        d = self.depth()
        
        f = open(filename+'.tex','w') 
        f.write("\documentclass{article}\n")
        f.write("\\usepackage{mathtools}\n")
        f.write("\\usepackage{xcolor}\n")
        f.write("\\usepackage[paperwidth="+str(5.+d*.3)+"in, paperheight="+str(2+n*0.2)+"in,margin=0.5in]{geometry}")
        f.write("\input{Qcircuit}\n")
        f.write("\\begin{document}\n")
        f.write("\\begin{equation*}\n") 
        #f.write("\Qcircuit @C=1.2em @R=0.5em {\n")
        f.write("\Qcircuit @C=1.0em @R=0.5em {\n")
        
        n = self.number_of_lines
        for q in range(0,n):
            qstring = '&'
            circuit_for_q = self.line_items[q]
            for gate in circuit_for_q:
                if gate.name == self.identity:
                    qstring += ' \qw &'
                elif gate.name == 'CNOT':
                    if gate.qubits[0] == q:
                        qstring += ' \ctrl{'+str(gate.qubits[1]-q)+'} &'
                    else:
                        qstring += ' \\targ &'
                elif gate.name == 'CPHASE':
                    if gate.qubits[0] == q:
                        qstring += ' \ctrl{'+str(gate.qubits[1]-q)+'} &'
                    else:
                        qstring += ' \control \qw &'
            
                else:
                    qstring += ' \gate{'+str(gate.name)+'} &'
                    
            qstring += ' \qw & \\'+'\\ \n'
            f.write(qstring)
        
        f.write("}\end{equation*}\n")
        f.write("\end{document}")
        f.close() 

    def copy(self):
        """
        Returns a copy of the circuit.
        """       
        return _copy.deepcopy(self)
        
    def combine_oneQgates(self, oneQgate_relations):
        """
        Compresses sequences of 1-qubit gates in the circuit, using the provided gate relations.
        One of the steps of the depth_compression() method, and in most cases that method will
        be more useful.
        
        Parameters
        ----------
        oneQgate_relations : dict
            Keys that are pairs of strings, corresponding to 1-qubit gate names, with values that are
            a single string, also corresponding to a 1-qubit gate name. Whenever a 1-qubit gate with 
            name `name1` is followed in the circuit by a 1-qubit gate with `name2` then, if 
            oneQgate_relations[name1,name2] = name3, name1 -> name3 and name2 -> self.identity, the
            identity name in the circuit. Moreover, this is still implemented when there are self.identity
            gates between these 1-qubit gates, and it is implemented iteratively in the sense that if there
            is a sequence of 1-qubit gates with names name1, name2, name3, ... and there are relations
            for all of (name1,name2) -> name12, (name12,name3) -> name123 etc then the entire sequence of
            1-qubit gates will be compressed into a single possibly non-idle 1-qubit gate followed by 
            idle gates in place of the previous 1-qubit gates.

            If a ProcessorSpec object has been created for the gates/device in question, the
            ProcessorSpec.oneQgate_relations is the appropriate (and auto-generated) `oneQgate_relations`.

            Note that this function will not compress sequences of 1-qubit gates that cannot be compressed by 
            independently inspecting sequential non-idle pairs (as would be the case with, for example, 
            Gxpi Gzpi Gxpi Gzpi, if the relation did not know that (Gxpi,Gzpi) -> Gypi, even though the sequence
            is the identity).
        
        Returns
        -------
        bool
            False if the circuit is unchanged, True otherwise.
        """ 
        assert(not self._static),"Cannot edit a read-only circuit!"
        # A flag that is turned to True if any non-trivial re-arranging is implemented by this method.
        compression_implemented = False        
        # Loop through all the qubits, to try and compress squences of 1-qubit gates on the qubit in question.
        for q in range(0,self.number_of_lines):
            # j keeps track of the layer of the *next* gate that we are going to try and combine with later gates.
            j = 0
            while j < self.depth()-1:
                # This is the label of the current gate that we are trying to combine with later gates.
                k = j
                # Check that the gate is a 1-qubit gate, because this function can only combine pairs of 1-qubit gates.
                if self.line_items[q][k].number_of_qubits == 1:
                    # Loop through the gates following this gate on qubit q.
                    for i in range(k+1,self.depth()):
                        # For each gate we try and combine we iterate j by 1: so we'll start the next loop at the gate
                        # we failed to combine with an earlier gate (unless we iterate j further)
                        j += 1
                        # If the next gate is not a 1-qubit gate, we leave the loop and try to combine the gate after it
                        # (the jth gate) with later gates. So we iterate j by 1 before leaving the loop
                        if self.line_items[q][i].number_of_qubits > 1:
                            j += 1
                            break
                        # If the next gate is a 1-qubit gate, we see if we can compress it with gate k.
                        else:                              
                            # The names of the gates to try and combine
                            gl1 = self.line_items[q][k].name
                            gl2 = self.line_items[q][i].name
                            # If the later gate is the identity we skip and move onto the next gate, because the combination would 
                            # be trivial.
                            if gl2 != self.identity:
                                # Try to find a label they combine to; if the pair is not in the algebra dictionary we don't succeed.
                                try:  
                                    new_gl1 = oneQgate_relations[gl1,gl2]
                                    new_gl2 = self.identity
                                    # Write in the new gate names.
                                    self.line_items[q][k] = _Label(new_gl1,self.line_labels[q])
                                    self.line_items[q][i] = _Label(new_gl2,self.line_labels[q])
                                    # Record that a compression has been implemented : the circuit has been changed.
                                    compression_implemented = True
                                # If we can't combine the gates we quit the loop -- because we can't try and combine the gate with
                                # a gate that is past this gate. But we don't iterate j, because perhaps this 1-qubit gate can be
                                # combined with later 1-qubit gates.
                                except:
                                    break
                # If the gate is not a 1-qubit gate we move on to the gate at the next circuit layer: so we iterate j by 1.
                else:
                    j += 1
        # Only if we've changed anything do we need to set the "dirty" atributes to True.
        if compression_implemented:
            self._tup_dirty = self._str_dirty = True
        # Returns the flag, so we know whether the algorithm achieved anything.
        return compression_implemented
    
    def shift_gates_forward(self):
        """
        All gates are shifted forwarded as far as is possible without any knowledge of what 
        any of the gates are, except that the self.identity gates (idle gates) can be replaced.
        One of the steps of the depth_compression() method.
        """
        assert(not self._static),"Cannot edit a read-only circuit!"
        # Keeps track of whether any changes have been made to the circuit.
        compression_implemented = False

        can_move_to_layer = _np.zeros(self.number_of_lines,int) 
        for q in range(0,self.number_of_lines):
            gate = self.line_items[q][0]
            if gate.name != self.identity:
                can_move_to_layer[q] = 1

        for j in range(1,self.depth()):
            for q in range(0,self.number_of_lines):
                gate = self.line_items[q][j]
                if gate.name != self.identity:
                    move_to_layer = 0
                    for qlabel in gate.qubits:
                        qindex = self.line_labels.index(qlabel)
                        move_to_layer = max(move_to_layer,can_move_to_layer[qindex])
                    
                    if move_to_layer < j:
                        for qlabel in gate.qubits:
                            qindex = self.line_labels.index(qlabel)
                            self.line_items[qindex][move_to_layer] = self.line_items[qindex][j]
                            self.line_items[qindex][j] = _Label(self.identity,qindex)
                            can_move_to_layer[qindex] = move_to_layer + 1
                    else:
                        for qlabel in gate.qubits:
                            qindex = self.line_labels.index(qlabel)
                            can_move_to_layer[qindex] = j + 1
        if return_flag:     
            return compression_implemented
        else:
            return
    
    def delete_idle_layers(self, return_flag=False):
        """
        Deletes all layers in the circuit that consist of only idle layers. One of the steps of the
        depth_compression() method. If return_flag is True, then a bool is returned that is True
        if and only if one or more layers have been deleted.
        """
        assert(not self._static),"Cannot edit a read-only circuit!"        
        compression_implemented = False
        
        d = self.depth()
        for i in range(0,d):
            
            layer = self.get_circuit_layer(d-1-i)
            all_idle = True
            
            for q in range(0,self.number_of_lines):
                if layer[q].name != self.identity:
                    all_idle = False
                    
            if all_idle:
                compression_implemented = True
                self.delete_layer(d-1-i)
        if return_flag:     
            return compression_implemented
        else:
            return
    
    
    def compress_depth(self, oneQgate_relations=None, verbosity=1):
        """
        Compresses the depth of a circuit using very simple re-write rules. 

        1. If `oneQgate_relations` is provided, all sequences of 1-qubit gates in the  circuit 
           are compressed as far as is possible using only the pair-wise combination rules
           provided by this dict (see below).
        2. All gates are shifted forwarded as far as is possible without any knowledge of what 
           any of the gates are, except that the self.identity gates (idle gates) can be replaced.
        3. All idle-only layers are deleted.
        
        Parameters
        ----------
        oneQgate_relations : dict
            Keys that are pairs of strings, corresponding to 1-qubit gate names, with values that are
            a single string, also corresponding to a 1-qubit gate name. Whenever a 1-qubit gate with 
            name `name1` is followed in the circuit by a 1-qubit gate with `name2` then, if 
            oneQgate_relations[name1,name2] = name3, name1 -> name3 and name2 -> self.identity, the
            identity name in the circuit. Moreover, this is still implemented when there are self.identity
            gates between these 1-qubit gates, and it is implemented iteratively in the sense that if there
            is a sequence of 1-qubit gates with names name1, name2, name3, ... and there are relations
            for all of (name1,name2) -> name12, (name12,name3) -> name123 etc then the entire sequence of
            1-qubit gates will be compressed into a single possibly non-idle 1-qubit gate followed by 
            idle gates in place of the previous 1-qubit gates.

            If a ProcessorSpec object has been created for the gates/device in question, the
            ProcessorSpec.oneQgate_relations is the appropriate (and auto-generated) `oneQgate_relations`.

            Note that this function will not compress sequences of 1-qubit gates that cannot be compressed by 
            independently inspecting sequential non-idle pairs (as would be the case with, for example, 
            Gxpi Gzpi Gxpi Gzpi, if the relation did not know that (Gxpi,Gzpi) -> Gypi, even though the sequence
            is the identity).

        verbosity : int, optional
            If > 0, information about the depth compression is printed to screen.
        
        Returns
        -------
        None
        """ 
        assert(not self._static),"Cannot edit a read-only circuit!"       
    
        if verbosity > 0:
            print("- Implementing circuit depth compression")
            print("  - Circuit depth before compression is {}".format(self.depth()))
               
        if oneQgate_relations is not None:                            
            flag1 = self.combine_oneQgates(oneQgate_relations)
        flag2 = self.shift_gates_forward()   
        flag3 = self.delete_idle_layers()
    
        if verbosity > 0:
            print("  - Circuit depth after compression is {}".format(self.depth()))       
    
    def simulate(self,gateset): #,inputstate=None,store=True,returnall=False):        
        """
        Compute the outcome probabilities of this Circuit using `gateset` as a
        model for the gates.

        Parameters
        ----------
        gateset : GateSet
            A description of the gate and SPAM operations corresponding to the
            labels stored in this Circuit.

        Returns
        -------
        probs : dictionary
            A dictionary with keys equal to the possible outcomes and values
            that are float probabilities.
        """
        return gateset.probs(self)

    
    def done_editing(self):
        """
        Make this Circuit read-only, so that it can be hashed (used as a
        dictionary key).  

        This is done automatically when attempting to hash a Circuit for the
        first time, so there's usually no need to call this function.

        Returns
        -------
        None
        """
        self._static = True
