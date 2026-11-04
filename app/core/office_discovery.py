"""Fail-closed configuration for the single explicitly designated provider."""
from dataclasses import dataclass,field
import os
from dotenv import dotenv_values
from app.config import ROOT
class DiscoveryError(RuntimeError):pass
@dataclass(frozen=True)
class DiscoverySettings:
 enabled:bool=False
 owner_sub:str=field(default='',repr=False)
 trigger_secret:str=field(default='',repr=False)
 def __post_init__(self):
  if type(self.enabled) is not bool or self.enabled and (not self.owner_sub or len(self.owner_sub)>255 or not self.trigger_secret.isascii() or len(self.trigger_secret)<32):raise ValueError('OFFICE_DISCOVERY_CONFIG')
 @classmethod
 def load(cls):
  v={**dotenv_values(ROOT/'.env'),**os.environ};flag=v.get('NKUST_OFFICE_DISCOVERY_ENABLED','0')
  if flag not in ('0','1'):raise ValueError('OFFICE_DISCOVERY_CONFIG')
  return cls(flag=='1',v.get('NKUST_OFFICE_DISCOVERY_OWNER_SUB') or '',v.get('NKUST_OFFICE_DISCOVERY_TRIGGER_SECRET') or '')
