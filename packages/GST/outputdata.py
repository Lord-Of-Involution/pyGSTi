""" Defines the OutputData class and supporting functions """
import cPickle as _pickle
from dataset import UpgradeOldDataSet as _UpgradeOldDataSet

class OutputData:
    """
    A collection of gatesets, datasets, and parameters for easy saving and loading.
    """
    def __init__(self, init_from_filename=None):
        """ Initialize an OutputData object, either empty by loading data from a file """
        self.datasets = { }
        self.gatesets = { }
        self.parameters = { }
        self.filename = init_from_filename
        
        if self.filename is not None:
            self.loadFrom(self.filename)

    def has_gateset(self, gsKey):
        """ Test whether this OutputData contains a gateset named gsKey"""
        return self.gatesets.has_key(gsKey)

    def has_dataset(self, dsKey):
        """ Test whether this OutputData contains a dataset named dsKey"""
        return self.datasets.has_key(dsKey)

    def get_gateset(self, gsKey):
        """ Returns the gateset named gsKey.  Returns None if no gateset of that name exists"""
        return self.gatesets.get(gsKey,None)
    
    def get_dataset(self, dsKey):
        """ Returns the dataset named dsKey.  Returns None if no dataset of that name exists"""
        return self.datasets[dsKey]

    def get_parameter(self, paramName, paramCategory=None):
        """
        Returns the parameter with name paramName, optionally constrained to the category paramCategory.
          If no parameter of that name is found, returns None.
        """
        if paramCategory is None:
            for (cat,cat_dict) in self.parameters.iteritems():
                if paramName in cat_dict:
                    return cat_dict[paramName]
        elif self.parameters.has_key(paramCategory):
            if paramName in self.parameters[paramCategory]:
                return self.parameters[paramCategory][paramName]
        return None

    def get_parameters(self, paramCategory):
        """ Returns the parameter dictionary corresponding to category paramCategory """
        return self.parameters[paramCategory]

    def set_gateset(self, gsKey, gateset):
        """ Stores a gateset with name gsKey """
        self.gatesets[gsKey] = gateset

    def set_gatesets(self, gsDict):
        """
        Stores gatesets using a dictionary with gateset names given by their dictionary keys
          and the gatesets themselves given by the dictionary values.
        """
        self.gatesets.update(gsDict)

    def set_dataset(self, dsKey, dataset):
        """ Stores a dataset with name dsKey """
        self.datasets[dsKey] = dataset

    def set_datasets(self, dsDict):
        """
        Stores datasets using a dictionary with dataset names given by their dictionary keys
          and the datasets themselves given by the dictionary values.
        """
        self.datasets.update(dsDict)
            
    def set_parameter(self, paramName, paramValue, paramCategory):
        """ Stores the value paramValue for the parameter named paramName within category paramCategory """
        if paramCategory not in self.parameters:
            self.parameters[paramCategory] = { paramName: paramValue }
        else:
            self.parameters[paramCategory][paramName] = paramValue

    def set_parameters(self, paramCategory, paramDict):
        """ Stores an entire dictionary of parameters paramDict as the category paramCategory """
        self.parameters[paramCategory] = paramDict



    def loadFrom(self, filename):
        """ Load data from a file.  If filename ends in .gz it will be gzip decompressed. """
        self.filename = filename

        #try:
        if filename.endswith(".gz"):
            import gzip
            file_data = _pickle.load(gzip.open(filename,'rb'))
        else:
            file_data = _pickle.load(open(filename,'rb'))
        #except:
        #    raise ValueError("Error loading pickle data from %s" % filename)
        version = file_data.get("gst_output_data_version",0)
        
        if version == 0:
            for (k,val) in file_data.iteritems():
                if   k == 'gst params': self.set_parameters('algorithm', val)
                elif k == 'data set params': self.set_parameters('dataset', val)
                elif k == 'data set': self.set_dataset('training', val)
                else: self.set_gateset(k, val)
                
        elif version == 1:
            for (k,val) in file_data.iteritems():
                if   k == 'gatesets': self.gatesets = val
                elif k == 'datasets': self.datasets = val
                elif k == 'parameters': self.parameters = val
                elif k == 'gst_output_data_version': continue
                else: raise ValueError("Invalid version 1 gst output data file: unknown key: %s" % k)
            
        else:
            raise ValueError("Unknown version (%s) of gst output data file" % version)
            

    def save(self):
        """ Save data to the same file this OutputData was loaded from """
        if self.filename is None:
            raise ValueError("Cannot save this OutputData object when it wasn't loaded from a file -- must use saveTo")
        return saveTo(self.filename)

    def saveTo(self, filename):
        """ Save data to a file.  If filename ends in .gz it will be gzip compressed. """
        dictToSave = { 'gatesets': self.gatesets,
                       'datasets': self.datasets,
                       'parameters': self.parameters,
                       'gst_output_data_version': 1 }
        if filename.endswith(".gz"):
            import gzip as _gzip
            _pickle.dump( dictToSave, _gzip.open(filename, "wb"))
        else:
            _pickle.dump( dictToSave, open(filename, "wb"))



#def UpgradeOldDataSets(outputDataWithOldDatasets):
#    newDatasets = { }
#    for key,oldDataset in outputDataWithOldDatasets.datasets.iteritems():
#        newDatasets[key] = _UpgradeOldDataSet(oldDataset)
#    outputDataWithOldDatasets.datasets = newDatasets
#
#def UpgradeOldDataSetPickle(filename):
#    import sys, DataSet, OldDataSet
#
#    currentDataSetModule = sys.modules['DataSet']
#    sys.modules['DataSet'] = OldDataSet  #replace DataSet module with old one so unpickling can work
#    try:      od = OutputData(filename)
#    finally:  sys.modules['DataSet'] = currentDataSetModule
#
#    od.UpgradeOldDataSets(od)
#    od.saveTo(filename + ".upd")
#
#    updated_od = OutputData(filename + ".upd")
#    for key,ds in updated_od.datasets.iteritems():
#        print "Upgraded dataset %s, %s" % (key, type(ds))
#
#    print "Successfully updated ==> %s" % (filename + ".upd")
    

