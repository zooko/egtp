from xmlrpclib import *
from interfaces import *
from binascii import *
from urllib import *
from tristero import *
from string import *

class TristeroLookup(ILookupManager):
    def __init__(this, url):
        this.url=url
        this.server=Server(url)

    def decap(this, s):
      s2=''
      for x in range(len(s)):
        if s[x] in uppercase:
          if not len(s2)==0:
            s2=s2+' '
          s2=s2+lower(s[x])
        else:
          s2=s2+s[x]
      return s2

    def lookup(this, key, lookuphand):
      oldkey=hexlify(key)
      key="mnet-node-id:"+oldkey
      token=this.server.search.search("<"+key+">", "", "", "file:nodes")
      results=this.server.search.fetch(token)
      val={}
      for part in results:
        pred=part[1]
        pred=split(pred, '#')[1]
        pred=this.decap(pred)
        otype=part[2][0]
        obj=part[2][1]
        if(otype==LITERAL):
          if pred=="sequence num":
            val[pred]=int(obj)
          else:
            val[pred]=obj
        elif pred=="broker id":
          obj=split(obj, ':')[1]
          obj=unhexlify(obj)
          val[pred]=obj
        elif pred=="connection strategies":
          key=oldkey+"-0"
          token=this.server.search.search("_:"+key, "", "", "file:nodes")
          results=this.server.search.fetch(token)
          subval={}
          for subpart in results:
            subpred=subpart[1]
            subpred=split(subpred, '#')[1]
            subpred=this.decap(subpred)
            otype=subpart[2][0]
            obj=subpart[2][1]
            if(otype==LITERAL):
              if subpred=='ip address':
                subval['IP address']=obj
              elif subpred=='comm strat sequence num':
                subval[subpred]=int(obj)
              else:
                subval[subpred]=obj
            elif subpred=="broker id":
              obj=split(obj, ':')[1]
              obj=unhexlify(obj)
              subval[subpred]=obj
            elif subpred=="pubkey":
              key=oldkey+"-0-pubkey"
              token=this.server.search.search("_:"+key, "", "", "file:nodes")
              results=this.server.search.fetch(token)
              pubval={}
              for pubpart in results:
                pubpred=pubpart[1]
                pubpred=split(pubpred, '#')[1]
                pubpred=this.decap(pubpred)
                otype=pubpart[2][0]
                obj=pubpart[2][1]
                if(otype==LITERAL):
                  pubval[pubpred]=obj
                elif pubpred=="key header":
                  key=oldkey+"-0-pubkey-header"
                  token=this.server.search.search("_:"+key, "", "", "file:nodes")
                  results=this.server.search.fetch(token)
                  headval={}
                  for headpart in results:
                    headpred=headpart[1]
                    headpred=split(headpred, '#')[1]
                    headpred=this.decap(headpred)
                    otype=headpart[2][0]
                    obj=headpart[2][1]
                    if otype==LITERAL:
                      headval[headpred]=obj
                    else:
                      print 'Unsupported header field:', headpred
                  pubval[pubpred]=headval
                elif pubpred=="key values":
                  key=oldkey+"-0-pubkey-value"
                  token=this.server.search.search("_:"+key, "", "", "file:nodes")
                  results=this.server.search.fetch(token)
                  valval={}
                  for valpart in results:
                    valpred=valpart[1]
                    valpred=split(valpred, '#')[1]
                    valpred=this.decap(valpred)
                    otype=valpart[2][0]
                    obj=valpart[2][1]
                    if otype==LITERAL:
                      valval[valpred]=obj
                    else:
                      print 'Unsupported value field:', valpred
                  pubval[pubpred]=valval
                else:
                  print 'Unsupported comm pub field:', pubpred
              subval[subpred]=pubval
            elif subpred=="lowerstrategy":
              key=oldkey+"-0-lower"
              token=this.server.search.search("_:"+key, "", "", "file:nodes")
              results=this.server.search.fetch(token)
              lowval={}
              for lowpart in results:
                lowpred=lowpart[1]
                lowpred=split(lowpred, '#')[1]
                lowpred=this.decap(lowpred)
                otype=lowpart[2][0]
                obj=lowpart[2][1]
                if(otype==LITERAL):
                  if lowpred=='ip address':
                    lowval['IP address']=obj
                  else:
                    lowval[lowpred]=obj
                elif lowpred=="broker id":
                  obj=split(obj, ':')[1]
                  obj=unhexlify(obj)
                  lowval[lowpred]=obj
                elif lowpred=="pubkey":
                  key=oldkey+"-0-pubkey"
                  token=this.server.search.search("_:"+key, "", "", "file:nodes")
                  results=this.server.search.fetch(token)
                  pubval={}
                  for pubpart in results:
                    pubpred=pubpart[1]
                    pubpred=split(pubpred, '#')[1]
                    pubpred=this.decap(pubpred)
                    otype=pubpart[2][0]
                    obj=pubpart[2][1]
                    if(otype==LITERAL):
                      puvval[pubpred]=obj
                    else:
                      print 'Unsupported pub field:', pubpred
                else:
                  print 'Unsupported low field:', lowpred
              subval[subpred]=lowval
            else:
              print 'Unsupported comm field:', subpred
          val[pred]=[subval]
        else:
          print 'Unsupported field:', pred
      lookuphand.result(val)

    def store(this, stype, sub, key, otype, obj):
      triple=[[stype, sub], key, [otype, obj]]
      this.server.search.add("file:nodes", triple)

    def publish(this, key, object):
      idStr=hexlify(key)
      id="mnet-node-id:"+idStr
      for key in object.keys():
        val=object[key];
        key=nodeSchema+join(split(key.title(), ' '), '')
        t=type(val)
        if(key==nodeSchema+"ConnectionStrategies"):
          for x in range(len(val)):
            subId=idStr+"-"+str(x)
            this.store(RESOURCE, id, key, NODE, subId)
            for subkey in val[x].keys():
              subval=val[x][subkey]
              subkey=commSchema+join(split(subkey.title(), ' '), '')
              if(subkey==commSchema+"BrokerId"):
                this.store(NODE, subId, subkey, RESOURCE, 'mnet-node-id:'+hexlify(subval))
              elif(type(subval)==type('str')):
                this.store(NODE, subId, subkey, LITERAL, subval)
              elif(type(subval)==type(1)):
                this.store(NODE, subId, subkey, LITERAL, str(subval))
              elif(subkey==commSchema+"Lowerstrategy"):
                lowId=subId+"-lower"
                this.store(NODE, subId, subkey, NODE, lowId)
                for lowkey in subval.keys():
                  lowval=subval[lowkey]
                  lowkey=lowerSchema+join(split(lowkey.title(), ' '), '')
                  if(lowkey==lowerSchema+'BrokerId'):
                    this.store(NODE, lowId, lowkey, RESOURCE, "mnet-node-id:"+hexlify(lowval))
                  elif(type(lowval)==type('str')):
                    this.store(NODE, lowId, lowkey, LITERAL, lowval)
                  elif(type(lowval)==type(1)):
                    this.store(NODE, lowId, lowkey, LITERAL, str(lowval))
                  else:
                    print 'Unsupported entry:', lowkey, type(lowval)
              elif(subkey==commSchema+"Pubkey"):
                subsubId=subId+"-pubkey"
                this.store(NODE, subId, subkey, NODE, subsubId)
                for subsubkey in subval.keys():
                  subsubval=subval[subsubkey]
                  subsubkey=pubkeySchema+join(split(subsubkey.title(), ' '), '')
                  if(subsubkey==pubkeySchema+"KeyHeader"):
                    headId=subsubId+"-header"
                    this.store(NODE, subsubId, subsubkey, NODE, headId)
                    for headkey in subsubval.keys():
                      headval=subsubval[headkey]
                      headkey=keyHeaderSchema+join(split(headkey.title(), ' '), '')
                      if(type(headval)==type('str')):
                        this.store(NODE, headId, headkey, LITERAL, headval)
                      else:
                        print 'Unsupported entry:', headkey
                  elif(subsubkey==pubkeySchema+"KeyValues"):
                    valId=subsubId+"-value"
                    this.store(NODE, subsubId, subsubkey, NODE, valId)
                    for valkey in subsubval.keys():
                      valval=subsubval[valkey]
                      valkey=keyValueSchema+join(split(valkey.title(), ' '), '')
                      if(type(valval)==type('str')):
                        this.store(NODE, valId, valkey, LITERAL, valval)
                      else:
                        print 'Unsupported entry:', valkey
                  else:
                    print 'Unsupported entry:', subsubkey
              else:
                print 'Unsupported entry:', subkey
        elif(t==type('str')):
          this.store(RESOURCE, id, key, LITERAL, val)
        elif(t==type(1)):
          this.store(RESOURCE, id, key, LITERAL, str(val))
        else:
          print 'Unsupported entry:', key
