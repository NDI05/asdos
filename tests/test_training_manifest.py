import pytest
from scripts.train_handwriting_local import validate

def sample(key,writer,split):
 return {'sample_id':key,'status':'human_confirmed','identity_free_crop_confirmed':True,'writer_id':writer,'split':split,'image_sha256':key}

def test_rejects_ai_labels_and_writer_leakage():
 with pytest.raises(ValueError,match='Unconfirmed'):
  validate([{'sample_id':'ai','status':'needs_human_confirmation'}])
 with pytest.raises(ValueError,match='leakage'):
  validate([sample('a','w1','train'),sample('b','w1','development')])

def test_accepts_separate_reviewed_writers():
 validate([sample('a','w1','train'),sample('b','w2','development')])
