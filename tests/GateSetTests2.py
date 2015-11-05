import unittest
import GST
import numpy as np
import warnings

class GateSetTestCase(unittest.TestCase):

    def setUp(self):
        self.gateset = GST.buildGateset( [2], [('Q0',)],['Gi','Gx','Gy'], 
                                         [ "I(Q0)","X(pi/8,Q0)", "Y(pi/8,Q0)"],
                                         rhoExpressions=["0"], EExpressions=["1"], 
                                         spamLabelDict={'plus': (0,0), 'minus': (-1,-1) })
        self.assertTrue(self.gateset.SPAMs['minus'] is None)

    def assertArraysAlmostEqual(self,a,b):
        self.assertAlmostEqual( np.linalg.norm(a-b), 0 )

    def assertNoWarnings(self, callable, *args, **kwds):
        with warnings.catch_warnings(record=True) as warning_list:
            warnings.simplefilter('always')
            result = callable(*args, **kwds)
            self.assertTrue(len(warning_list) == 0)
        return result


class TestGateSetMethods(GateSetTestCase):

  def test_creation(self):
      self.assertIsInstance(self.gateset, GST.GateSet)

  def test_counting(self):

      self.assertEqual(self.gateset.getNumRhoVecs(), 1) 
      self.assertEqual(self.gateset.getNumEVecs(), 1) 

      for gates in (True,False):
          for G0 in (True,False):
              for SPAM in (True,False):
                  for SP0 in (True,False):
                      nGates = 3 if gates else 0
                      nParamsPerGate = 16 if G0 else 12
                      nSPVecs = 1 if SPAM else 0
                      nEVecs = 1 if SPAM else 0
                      nParamsPerSP = 4 if SP0 else 3
                      nParams =  nGates * nParamsPerGate + nSPVecs * nParamsPerSP + nEVecs * 4
                      self.assertEqual(self.gateset.getNumParams(gates,G0,SPAM,SP0), nParams)  

      self.assertEqual(self.gateset.getRhoVecIndices(), [0]) 
      self.assertEqual(self.gateset.getEVecIndices(), [0]) 

      self.gateset.log("Test Log Message")


  def test_getset(self):

      v = np.array( [[1],[2],[3],[4]], 'd')
      
      self.gateset.set_identityVec(v)
      w = self.gateset.get_identityVec()
      self.assertArraysAlmostEqual(w,v)

      self.gateset.set_rhoVec(v,index=1)
      w = self.gateset.get_rhoVec(index=1)
      self.assertArraysAlmostEqual(w,v)

      self.gateset.set_EVec(v,index=1)
      w = self.gateset.get_EVec(index=1)
      self.assertArraysAlmostEqual(w,v)

      self.gateset.add_SPAM_label(0,1,"TEST")
      self.assertTrue("TEST" in self.gateset.get_SPAM_labels())
      d = self.gateset.get_SPAM_label_dict()
      self.assertEqual( d[(0,1)], "TEST" )

      Gi_matrix = np.identity(4, 'd')
      self.assertTrue( isinstance(self.gateset.get_gate('Gi'), GST.Gate.FullyParameterizedGate) )
      self.assertTrue( isinstance(self.gateset['Gi'], np.ndarray) )

      Gi_test_matrix = np.random.random( (4,4) )
      Gi_test = GST.Gate.FullyParameterizedGate( Gi_test_matrix  )
      self.gateset.set_gate("Gi", Gi_test)
      self.assertArraysAlmostEqual( self.gateset['Gi'], Gi_test_matrix )


  def test_copy(self):
      cp = self.gateset.copy()
      self.assertAlmostEqual( self.gateset.diff_Frobenius(cp), 0 )
      self.assertAlmostEqual( self.gateset.diff_JTraceDistance(cp), 0 )


  def test_vectorize(self):
      cp = self.gateset.copy()
      for gates in (True,False):
          for G0 in (True,False):
              for SPAM in (True,False):
                  for SP0 in (True,False):
                      v = cp.toVector(gates, G0, SPAM, SP0 )
                      cp.fromVector(v, gates, G0, SPAM, SP0)
                      self.assertAlmostEqual( self.gateset.diff_Frobenius(cp), 0 )


  def test_transform(self):
      T = np.array([[ 0.36862036,  0.49241519,  0.35903944,  0.90069522],
                    [ 0.12347698,  0.45060548,  0.61671491,  0.64854769],
                    [ 0.4038386 ,  0.89518315,  0.20206879,  0.6484708 ],
                    [ 0.44878029,  0.42095514,  0.27645424,  0.41766033]]) #some random array
      Tinv = np.linalg.inv(T)
      cp = self.gateset.copy()
      cp.transform(T,Tinv)

      self.assertAlmostEqual( self.gateset.diff_Frobenius(cp, T), 0 )
      self.assertAlmostEqual( self.gateset.diff_JTraceDistance(cp, T), 0 )

      for gateLabel in cp:
          self.assertArraysAlmostEqual(cp[gateLabel], np.dot(Tinv, np.dot(self.gateset[gateLabel], T)))
      for i in range(len(cp.rhoVecs)):
          self.assertArraysAlmostEqual(cp.rhoVecs[i], np.dot(Tinv, self.gateset.rhoVecs[i]))
      for i in range(len(cp.EVecs)):
          self.assertArraysAlmostEqual(cp.EVecs[i], np.dot(np.transpose(T), self.gateset.EVecs[i]))      
      

  def test_simple_multiplicationA(self):
      gatestring = ('Gx','Gy')
      p1 = np.dot( self.gateset['Gy'], self.gateset['Gx'] )
      p2 = self.gateset.product(gatestring, bScale=False)
      p3,scale = self.gateset.product(gatestring, bScale=True)
      self.assertArraysAlmostEqual(p1,p2)
      self.assertArraysAlmostEqual(p1,scale*p3)

  def test_simple_multiplicationB(self):
      gatestring = ('Gx','Gy','Gy')
      p1 = np.dot( self.gateset['Gy'], np.dot( self.gateset['Gy'], self.gateset['Gx'] ))
      p2 = self.gateset.product(gatestring, bScale=False)
      p3,scale = self.gateset.product(gatestring, bScale=True)
      self.assertArraysAlmostEqual(p1,p2)
      self.assertArraysAlmostEqual(p1,scale*p3)

  def test_bulk_multiplication(self):
      gatestring1 = ('Gx','Gy')
      gatestring2 = ('Gx','Gy','Gy')
      evt = self.gateset.Bulk_evalTree( [gatestring1,gatestring2] )      

      p1 = np.dot( self.gateset['Gy'], self.gateset['Gx'] )
      p2 = np.dot( self.gateset['Gy'], np.dot( self.gateset['Gy'], self.gateset['Gx'] ))

      bulk_prods = self.gateset.Bulk_Product(evt)
      bulk_prods_scaled, scaleVals = self.gateset.Bulk_Product(evt, bScale=True)
      bulk_prods2 = scaleVals[:,None,None] * bulk_prods_scaled
      self.assertArraysAlmostEqual(bulk_prods[0],p1)
      self.assertArraysAlmostEqual(bulk_prods[1],p2)
      self.assertArraysAlmostEqual(bulk_prods2[0],p1)
      self.assertArraysAlmostEqual(bulk_prods2[1],p2)

  def test_simple_probabilityA(self):
      gatestring = ('Gx','Gy')
      p1 = np.dot( np.transpose(self.gateset.EVecs[0]),
                   np.dot( self.gateset['Gy'],
                           np.dot(self.gateset['Gx'],
                                  self.gateset.rhoVecs[0])))
      p2 = self.gateset.Pr('plus',gatestring)
      self.assertArraysAlmostEqual(p1,p2)

  def test_simple_probabilityB(self):
      gatestring = ('Gx','Gy','Gy')
      p1 = np.dot( np.transpose(self.gateset.EVecs[0]), 
                   np.dot( self.gateset['Gy'], 
                           np.dot( self.gateset['Gy'], 
                                   np.dot(self.gateset['Gx'], 
                                          self.gateset.rhoVecs[0]))))
      p2 = self.gateset.Pr('plus',gatestring)
      self.assertAlmostEqual(p1,p2)

  def test_bulk_probabilities(self):
      gatestring1 = ('Gx','Gy')
      gatestring2 = ('Gx','Gy','Gy')
      evt = self.gateset.Bulk_evalTree( [gatestring1,gatestring2] )      

      p1 = np.dot( np.transpose(self.gateset.EVecs[0]),
                   np.dot( self.gateset['Gy'],
                           np.dot(self.gateset['Gx'],
                                  self.gateset.rhoVecs[0])))

      p2 = np.dot( np.transpose(self.gateset.EVecs[0]), 
                   np.dot( self.gateset['Gy'], 
                           np.dot( self.gateset['Gy'], 
                                   np.dot(self.gateset['Gx'], 
                                          self.gateset.rhoVecs[0]))))

      #check == true could raise a warning if a mismatch is detected
      bulk_pr = self.assertNoWarnings(self.gateset.Bulk_Pr,'plus',evt,check=True)
      bulk_pr_m = self.assertNoWarnings(self.gateset.Bulk_Pr,'minus',evt,check=True)
      self.assertAlmostEqual(bulk_pr[0],p1)
      self.assertAlmostEqual(bulk_pr[1],p2)
      self.assertAlmostEqual(bulk_pr_m[0],1.0-p1)
      self.assertAlmostEqual(bulk_pr_m[1],1.0-p2)

      probs1 = self.gateset.Probs(gatestring1)
      probs2 = self.gateset.Probs(gatestring2)
      self.assertAlmostEqual(probs1['plus'],p1)
      self.assertAlmostEqual(probs2['plus'],p2)
      self.assertAlmostEqual(probs1['minus'],1.0-p1)
      self.assertAlmostEqual(probs2['minus'],1.0-p2)

      bulk_probs = self.assertNoWarnings(self.gateset.Bulk_Probs,evt,check=True)
      self.assertAlmostEqual(bulk_probs['plus'][0],p1)
      self.assertAlmostEqual(bulk_probs['plus'][1],p2)
      self.assertAlmostEqual(bulk_probs['minus'][0],1.0-p1)
      self.assertAlmostEqual(bulk_probs['minus'][1],1.0-p2)

      nGateStrings = 2; nSpamLabels = 2
      probs_to_fill = np.empty( (nSpamLabels,nGateStrings), 'd')
      spam_label_rows = { 'plus': 0, 'minus': 1 }
      self.assertNoWarnings(self.gateset.Bulk_fillProbs, probs_to_fill, spam_label_rows, evt, check=True)
      self.assertAlmostEqual(probs_to_fill[0,0],p1)
      self.assertAlmostEqual(probs_to_fill[0,1],p2)
      self.assertAlmostEqual(probs_to_fill[1,0],1-p1)
      self.assertAlmostEqual(probs_to_fill[1,1],1-p2)

      prods = self.gateset.Bulk_Product(evt) #TODO: test output?


  def test_derivatives(self):
      gatestring0 = ('Gi','Gx')
      gatestring1 = ('Gx','Gy')
      gatestring2 = ('Gx','Gy','Gy')

      evt = self.gateset.Bulk_evalTree( [gatestring0,gatestring1,gatestring2] )

      dP0 = self.gateset.dPr("plus", gatestring0)
      dP1 = self.gateset.dPr("plus", gatestring1)
      dP2 = self.gateset.dPr("plus", gatestring2)
      #dP0m = self.gateset.dPr("minus", gatestring0)
      #dP1m = self.gateset.dPr("minus", gatestring1)
      #dP2m = self.gateset.dPr("minus", gatestring2)

      bulk_dP = self.gateset.Bulk_dPr("plus", evt, returnPr=False, check=True)
      #bulk_dP_m = self.gateset.Bulk_dPr("minus", evt, returnPr=False, check=True)
      bulk_dP_chk, bulk_P = self.gateset.Bulk_dPr("plus", evt, returnPr=True, check=False)
      self.assertArraysAlmostEqual(bulk_dP,bulk_dP_chk)
      self.assertArraysAlmostEqual(bulk_dP[0,:],dP0)
      self.assertArraysAlmostEqual(bulk_dP[1,:],dP1)
      self.assertArraysAlmostEqual(bulk_dP[2,:],dP2)
      #self.assertArraysAlmostEqual(bulk_dP_m[0,:],dP0m)
      #self.assertArraysAlmostEqual(bulk_dP_m[1,:],dP1m)
      #self.assertArraysAlmostEqual(bulk_dP_m[2,:],dP2m)



      dProbs0 = self.gateset.dProbs(gatestring0)
      dProbs1 = self.gateset.dProbs(gatestring1)
      dProbs2 = self.gateset.dProbs(gatestring2)
      bulk_dProbs = self.gateset.Bulk_dProbs(evt, returnPr=False, check=True)
      bulk_dProbs_chk = self.gateset.Bulk_dProbs(evt, returnPr=True, check=True)
      self.assertArraysAlmostEqual(bulk_dProbs['plus'],bulk_dProbs_chk['plus'][0])
      self.assertArraysAlmostEqual(bulk_dProbs['plus'][0,:],dP0)
      self.assertArraysAlmostEqual(bulk_dProbs['plus'][1,:],dP1)
      self.assertArraysAlmostEqual(bulk_dProbs['plus'][2,:],dP2)
      self.assertArraysAlmostEqual(bulk_dProbs['plus'][0,:],dProbs0['plus'])
      self.assertArraysAlmostEqual(bulk_dProbs['plus'][1,:],dProbs1['plus'])
      self.assertArraysAlmostEqual(bulk_dProbs['plus'][2,:],dProbs2['plus'])


      nGateStrings = 3; nSpamLabels = 2; nParams = self.gateset.getNumParams()
      probs_to_fill = np.empty( (nSpamLabels,nGateStrings), 'd')
      dprobs_to_fill = np.empty( (nSpamLabels,nGateStrings,nParams), 'd')
      dprobs_to_fillB = np.empty( (nSpamLabels,nGateStrings,nParams), 'd')
      spam_label_rows = { 'plus': 0, 'minus': 1 }
      self.assertNoWarnings(self.gateset.Bulk_filldProbs, dprobs_to_fill, spam_label_rows, evt,
                            prMxToFill=probs_to_fill,check=True)
      self.assertArraysAlmostEqual(dprobs_to_fill[0,0,:],dP0)
      self.assertArraysAlmostEqual(dprobs_to_fill[0,1,:],dP1)
      self.assertArraysAlmostEqual(dprobs_to_fill[0,2,:],dP2)

      #without probs
      self.assertNoWarnings(self.gateset.Bulk_filldProbs, dprobs_to_fillB, spam_label_rows, evt, check=True)
      self.assertArraysAlmostEqual(dprobs_to_fill,dprobs_to_fillB)


      dProds = self.gateset.Bulk_dProduct(evt) #TODO: test output?


  def test_hessians(self):
      gatestring0 = ('Gi','Gx')
      gatestring1 = ('Gx','Gy')
      gatestring2 = ('Gx','Gy','Gy')

      evt = self.gateset.Bulk_evalTree( [gatestring0,gatestring1,gatestring2] )

      hP0 = self.gateset.hPr("plus", gatestring0)
      hP1 = self.gateset.hPr("plus", gatestring1)
      hP2 = self.gateset.hPr("plus", gatestring2)
      #hP0m = self.gateset.hPr("minus", gatestring0)
      #hP1m = self.gateset.hPr("minus", gatestring1)
      #hP2m = self.gateset.hPr("minus", gatestring2)

      bulk_hP = self.gateset.Bulk_hPr("plus", evt, returnPr=False, returnDeriv=False, check=True)
      #bulk_hP_m = self.gateset.Bulk_hPr("minus", evt, returnPr=False, returnDeriv=False, check=True)
      bulk_hP_chk, bulk_dP, bulk_P = self.gateset.Bulk_hPr("plus", evt, returnPr=True, returnDeriv=True, check=False)
      self.assertArraysAlmostEqual(bulk_hP,bulk_hP_chk)
      self.assertArraysAlmostEqual(bulk_hP[0,:,:],hP0)
      self.assertArraysAlmostEqual(bulk_hP[1,:,:],hP1)
      self.assertArraysAlmostEqual(bulk_hP[2,:,:],hP2)
      #self.assertArraysAlmostEqual(bulk_hP_m[0,:,:],hP0m)
      #self.assertArraysAlmostEqual(bulk_hP_m[1,:,:],hP1m)
      #self.assertArraysAlmostEqual(bulk_hP_m[2,:,:],hP2m)

      hProbs0 = self.gateset.hProbs(gatestring0)
      hProbs1 = self.gateset.hProbs(gatestring1)
      hProbs2 = self.gateset.hProbs(gatestring2)
      bulk_hProbs = self.gateset.Bulk_hProbs(evt, returnPr=False, check=True)
      bulk_hProbs_chk = self.gateset.Bulk_hProbs(evt, returnPr=True, check=True)
      self.assertArraysAlmostEqual(bulk_hProbs['plus'],bulk_hProbs_chk['plus'][0])
      self.assertArraysAlmostEqual(bulk_hProbs['plus'][0,:,:],hP0)
      self.assertArraysAlmostEqual(bulk_hProbs['plus'][1,:,:],hP1)
      self.assertArraysAlmostEqual(bulk_hProbs['plus'][2,:,:],hP2)
      self.assertArraysAlmostEqual(bulk_hProbs['plus'][0,:,:],hProbs0['plus'])
      self.assertArraysAlmostEqual(bulk_hProbs['plus'][1,:,:],hProbs1['plus'])
      self.assertArraysAlmostEqual(bulk_hProbs['plus'][2,:,:],hProbs2['plus'])

      nGateStrings = 3; nSpamLabels = 2; nParams = self.gateset.getNumParams()
      probs_to_fill = np.empty( (nSpamLabels,nGateStrings), 'd')
      probs_to_fillB = np.empty( (nSpamLabels,nGateStrings), 'd')
      dprobs_to_fill = np.empty( (nSpamLabels,nGateStrings,nParams), 'd')
      dprobs_to_fillB = np.empty( (nSpamLabels,nGateStrings,nParams), 'd')
      hprobs_to_fill = np.empty( (nSpamLabels,nGateStrings,nParams,nParams), 'd')
      hprobs_to_fillB = np.empty( (nSpamLabels,nGateStrings,nParams,nParams), 'd')
      spam_label_rows = { 'plus': 0, 'minus': 1 }
      self.assertNoWarnings(self.gateset.Bulk_fillhProbs, hprobs_to_fill, spam_label_rows, evt,
                            prMxToFill=probs_to_fill, derivMxToFill=dprobs_to_fill, check=True)

      self.assertArraysAlmostEqual(hprobs_to_fill[0,0,:,:],hP0)
      self.assertArraysAlmostEqual(hprobs_to_fill[0,1,:,:],hP1)
      self.assertArraysAlmostEqual(hprobs_to_fill[0,2,:,:],hP2)

      #without derivative
      self.assertNoWarnings(self.gateset.Bulk_fillhProbs, hprobs_to_fillB, spam_label_rows, evt,
                            prMxToFill=probs_to_fillB, check=True) 
      self.assertArraysAlmostEqual(hprobs_to_fill,hprobs_to_fillB)
      self.assertArraysAlmostEqual(probs_to_fill,probs_to_fillB)

      #without probs
      self.assertNoWarnings(self.gateset.Bulk_fillhProbs, hprobs_to_fillB, spam_label_rows, evt,
                            derivMxToFill=dprobs_to_fillB, check=True) 
      self.assertArraysAlmostEqual(hprobs_to_fill,hprobs_to_fillB)
      self.assertArraysAlmostEqual(dprobs_to_fill,dprobs_to_fillB)

      #without either
      N = self.gateset.gate_dim**2 #number of elements in a gate matrix
      
      hProds = self.gateset.Bulk_hProduct(evt)
      hProdsB,scales = self.gateset.Bulk_hProduct(evt, bScale=True)
      self.assertArraysAlmostEqual(hProds, scales[:,None,None,None,None]*hProdsB)

      hProdsFlat = self.gateset.Bulk_hProduct(evt, flat=True, bScale=False)
      hProdsFlatB,S1 = self.gateset.Bulk_hProduct(evt, flat=True, bScale=True)
      self.assertArraysAlmostEqual(hProdsFlat, np.repeat(S1,N)[:,None,None]*hProdsFlatB)

      hProdsC, dProdsC, prodsC = self.gateset.Bulk_hProduct(evt, bReturnDProdsAndProds=True, bScale=False)
      hProdsD, dProdsD, prodsD, S2 = self.gateset.Bulk_hProduct(evt, bReturnDProdsAndProds=True, bScale=True)
      self.assertArraysAlmostEqual(hProds, hProdsC)
      self.assertArraysAlmostEqual(hProds, S2[:,None,None,None,None]*hProdsD)
      self.assertArraysAlmostEqual(dProdsC, S2[:,None,None,None]*dProdsD)
      self.assertArraysAlmostEqual(prodsC, S2[:,None,None]*prodsD)

      hProdsF, dProdsF, prodsF    = self.gateset.Bulk_hProduct(evt, bReturnDProdsAndProds=True, flat=True, bScale=False)
      hProdsF2, dProdsF2, prodsF2, S3 = self.gateset.Bulk_hProduct(evt, bReturnDProdsAndProds=True, flat=True, bScale=True)
      self.assertArraysAlmostEqual(hProdsFlat, hProdsF)
      self.assertArraysAlmostEqual(hProdsFlat, np.repeat(S3,N)[:,None,None]*hProdsF2)
      self.assertArraysAlmostEqual(dProdsF, np.repeat(S3,N)[:,None]*dProdsF2)
      self.assertArraysAlmostEqual(prodsF, S3[:,None,None]*prodsF2)


  def test_failures(self):
      
      with self.assertRaises(KeyError):
          self.gateset['Non-existent-key']

      with self.assertRaises(ValueError):
          self.gateset['Gx'] = np.zeros((4,4),'d') #can't set matrices

      with self.assertRaises(ValueError):
          self.gateset.update( {'Gx': np.zeros((4,4),'d') } )

      with self.assertRaises(ValueError):
          self.gateset.setdefault('Gx',np.zeros((4,4),'d'))

          
      



      
if __name__ == "__main__":
    unittest.main(verbosity=2)
