import requests
import pprint
import pickle
from datetime import datetime, timezone, timedelta
import os
import json

CACHE_DIR = "./cache"
CSV_DIR = "./csv"

DEFAULT_DAYS = 7

class Up():

  def __init__(self, token):
    self.url_prefix = "https://api.up.com.au/api/v1"
    self.headers = {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + token,
    }
    self.now = datetime.now(timezone.utc).astimezone()
    self.today = (self.now.isoformat())[0:10]
    self.stateload()
    self.ping()

  def get(self, point):
    api_url = self.url_prefix + point
    response = requests.get(api_url, headers=self.headers)
    return response.json()

  def getpaged(self, point, params, cachestr,cache=True):
    filepath = CACHE_DIR + point + "/"
    filename = filepath + "getpaged-" + cachestr + ".pickle"
    if not os.path.isdir(filepath):
      os.makedirs(filepath)
    if cache and os.path.isfile(filename):
      with open(filename, 'rb') as file:
        data = pickle.load(file)
    else:
      api_url = self.url_prefix + point
      response = requests.get(api_url, headers=self.headers, params=params)
      if not response.ok:
        print(response)
        print(response.reason)
        print(response.text)
      rawdata = response.json()
      data = rawdata["data"]
      while rawdata["links"]["next"]:
        print(".", end="")
        response = requests.get(rawdata["links"]["next"], headers=self.headers)
        rawdata = response.json()
        data.extend(rawdata["data"])
      print("")
      with open(filename, 'wb') as file:
        pickle.dump(data, file, pickle.HIGHEST_PROTOCOL)
    return data

  def patchcat(self, id, cat):
    api_url = self.url_prefix + "/transactions/" + id + "/relationships/category"
    patch = {"data": {"type": "categories", "id": cat}}
    p = requests.patch(api_url, json.dumps(patch), headers=self.headers)
    print(p)
    return p

  def ping(self):
    x = self.get("/util/ping")
    print(x["meta"]["statusEmoji"])

  def accounts(self):
    print("ACCOUNTS")
    acc = self.get("/accounts")
    for x in acc["data"]:
      print("{:>10} - {}".format(x["attributes"]["balance"]["value"],
                                 x["attributes"]["displayName"]))

  def getcategories(self, Print=False):
    if not hasattr(self,"categories"):
      cat = self.get("/categories")
      self.categories = {"other": "Other"}
      for x in cat["data"]:
        if x["relationships"]["parent"]["data"] is not None:
          self.categories[x["id"]] = x["attributes"]["name"]
    if Print:
      print("GET CATEGORIES")
      for x in self.categories:
        print("{:>35} - {:<35}".format(
          x, self.categories[x]))

  def gettransactions(self, mode, cache=True):
    print("TRANSACTIONS")
    if type(mode) == int:
      first = datetime(mode, 1, 1, 0, 0).astimezone()
      last = datetime(mode, 12, 31, 23, 59).astimezone()
      filter = {
        "filter[since]": first.isoformat(),
        "filter[until]": last.isoformat(),
      }
      data = self.getpaged("/transactions", filter, "YR=" + str(mode),cache=cache)
    if mode == "all":
      DAYS = 9999
      data = self.getpaged("/transactions",
                           {"filter[since]": self.now - timedelta(days=DAYS)},
                           self.today + "-" + "DAYS=" + str(DAYS),cache=cache)
    if mode == "recent":
      print("Now     : " + self.now.isoformat())
      print("Last run: " + self.state["lastrun"].isoformat())
      data = self.getpaged("/transactions",
                           {"filter[since]": self.state["lastrun"]}, self.today + "-" + "RECENT",cache=cache)
    if mode == "week":
      DAYS = 7
      data = self.getpaged("/transactions",
                           {"filter[since]": self.now - timedelta(days=DAYS)},
                           self.today + "-" + "DAYS=" + str(DAYS),cache=cache)
    if mode == "month":
      DAYS = 28
      data = self.getpaged("/transactions",
                           {"filter[since]": self.now - timedelta(days=DAYS)},
                           self.today + "-" + "DAYS=" + str(DAYS),cache=cache)
    if mode == "year":
      DAYS = 365
      data = self.getpaged("/transactions",
                           {"filter[since]": self.now - timedelta(days=DAYS)},
                           self.today + "-" + "DAYS=" + str(DAYS),cache=cache)
    c = 0
    for x in data:
      c = c + 1
    print("#: " + str(c))
    return data

  def show(self, data):
    print("SHOW TRANSACTIONS")
    for x in data:
      att = x["attributes"]
      rel = x["relationships"]
      amount = att["amount"]["valueInBaseUnits"]
      parcat = rel["parentCategory"]["data"]
      cat = rel["category"]["data"]
      if parcat is None:
        parcat = "none"
      else:
        parcat = parcat["id"]
      if cat is None:
        cat = "none"
      else:
        cat = cat["id"]
      print(att["createdAt"][0:10], att["description"], att["amount"]["value"],
            parcat, cat)


  def summarise(self, data, OtherThresh=0.01):
    print("SUMMARISE TRANSACTIONS")
    catsumm = self.catsummary(data)
    shortcat = self.summaryfindother(catsumm, OtherThresh=OtherThresh)
    shortsumm = self.summaryshorten(catsumm,shortcat)

    # self.summaryprint(catsumm,heading="FULL SUMMARY",filename="upsummaryfull.csv")
    self.summaryprint(shortsumm,heading="SHORT SUMMARY",filename="upsummary.csv")
    
    return shortsumm
    
  def catsummary(self, data):
    categorytotals = {}
    categorycount = {}
    incometotals = {}
    for x in data:
      att = x["attributes"]
      amount = att["amount"]["valueInBaseUnits"]
      cat = self.checktranscat(x)
      if cat is not None:
        subtotal = categorytotals.get(cat)
        if subtotal is None: subtotal = 0
        categorytotals[cat] = subtotal + amount / 100
        if categorycount.get(cat) is None: categorycount[cat] = 0
        categorycount[cat] = categorycount[cat] + 1
    for ii in categorytotals:
      categorytotals[ii] = round(categorytotals[ii])
    categorytotals = dict(
      sorted(categorytotals.items(), key=lambda item: item[1]))
    spendingsubtotal = 0
    spendingtotal = 0
    incometotal = 0
    for ii in categorytotals:
      if ii is not None and categorytotals[ii] < 0:
        if not(ii=="investments"):
          spendingsubtotal = categorytotals[ii] + spendingsubtotal
        spendingtotal = categorytotals[ii] + spendingtotal
      if ii is not None and categorytotals[ii] > 0:
        incometotal = categorytotals[ii] + incometotal
              
    return {
      "spendtotal": spendingtotal,
      "spendsubtotal": spendingsubtotal,
      "incometotal": incometotal,
      "subtotals": categorytotals,
      "counts": categorycount,
      }
  
  def summaryfindother(self,catsumm, OtherThresh=0.01):
    thresh = abs(catsumm["spendtotal"]*OtherThresh)
    shortcat = {}
    for ii in catsumm["subtotals"]:
      if ii is not None:
        if abs(catsumm["subtotals"][ii]) > abs(thresh):
          shortcat[ii] = True
    return shortcat

  
  def summaryshorten(self,catsumm,shortcat):
    shorttotals = {}
    shortcounts = {}
    shorttotals["other"] = 0
    shortcounts["other"] = 0
    for ii in catsumm["subtotals"]:
      cattot = catsumm["subtotals"][ii]
      catcnt = catsumm["counts"][ii]
      if shortcat.get(ii) is not None:
        shorttotals[ii] = cattot
        shortcounts[ii] = catcnt
      else:
        shorttotals["other"] = shorttotals["other"] + cattot
        shortcounts["other"] = shortcounts["other"] + catcnt
    shorttotals = dict(sorted(shorttotals.items(), key=lambda item: item[1]))

    return {
      "spendtotal": catsumm["spendtotal"],
      "spendsubtotal": catsumm["spendsubtotal"],
      "incometotal": catsumm["incometotal"],
      "subtotals": shorttotals,
      "counts": shortcounts,
      }

  def summaryprint(self,catsumm,filename="upsummary.csv",heading="SUMMARY"):
    filepath = CSV_DIR + "/"
    if not os.path.isdir(filepath):
      os.makedirs(filepath)
    
    print("{:>25}  {:>6}  {:>6}".format(
      "Spending", 
      str(round(
        100*catsumm["spendsubtotal"]/catsumm["incometotal"]
        ))+"%", 
      catsumm["spendsubtotal"]
      ))
    print("{:>25}  {:>6}  {:>6}".format(
      "Investments",
      str(round(
        100*catsumm["subtotals"]["investments"]/catsumm["incometotal"]
        ))+"%",
        catsumm["subtotals"]["investments"]
      ))
    print("{:>25}  {:>6}  {:>6}".format(
      "Total", 
      str(round(
        100*catsumm["spendtotal"]/catsumm["incometotal"]
        ))+"%", 
      catsumm["spendtotal"]
      ))
    print("{:>25}  {:>6}  {:>6}".format(
      "Income", "100%", catsumm["incometotal"]
      ))
    print("{:>25}  {:>6}  {:>6}".format(
      "Net", 
      str(round(
        100*(catsumm["incometotal"]+catsumm["spendtotal"])/catsumm["incometotal"]
        ))+"%", 
      catsumm["incometotal"]+catsumm["spendtotal"]
      ))
    print("")
    
    print(heading)
    with open(CSV_DIR + "/" + filename, "w") as file:
      file.write("CATEGORY,COUNT,TOTAL\n")
      for ii in catsumm["subtotals"]:
        if ii is not None:
          file.write(ii + "," +
            str(catsumm["counts"][ii]) + "," +
            str(abs(catsumm["subtotals"][ii])) + "\n")
          print("{:>25}  {:>6}  {:>6}".format(ii[0:24], catsumm["counts"][ii],catsumm["subtotals"][ii]))



  def checktranscat(self,x):
    att = x["attributes"]
    rel = x["relationships"]
    amount = att["amount"]["valueInBaseUnits"]
    cat = rel["category"]["data"]
    tags = rel["tags"]["data"]
    tax = att["description"] == "Withholding Tax"
    ignore = False
    if len(tags) > 0:
      ignore = tags[0]["id"] == "ignore"
    notTransfer = rel["transferAccount"]["data"] is None
    if ignore:
      cat = None
    else:
      if notTransfer:
        if (cat is None):
          if (amount > 0) or tax:
            cat = "income"
          else:
            cat = "none"
            print(att["createdAt"][0:10], att["description"],
                  att["amount"]["value"])
        else:
          cat = cat["id"]
    return cat





  def compare(self, data, OtherThresh=0.01):
    print("COMPARE TRANSACTIONS")
    categorytotals = {}
    categorycount = {}
    spendingtotal = {}
    spendingsubtotal = {}

    firstper = list(data)[0]

    catsumm = self.catsummary(data[firstper])
    shortcat = self.summaryfindother(catsumm,
      OtherThresh=OtherThresh)
    
    for per in data:
      categorytotals[per] = {}
      categorycount[per] = {}
      catsumm = self.catsummary(data[per])
      shortsumm = self.summaryshorten(catsumm,shortcat)
      summ = shortsumm
      categorytotals[per]   = summ["subtotals"]
      categorycount[per]    = summ["counts"]
      spendingtotal[per]    = summ["spendtotal"]
      spendingsubtotal[per] = summ["spendsubtotal"]
          
    allcat = {}
    for per in categorytotals:
      for c in categorytotals[per]:
        allcat[c] = True
      
    for per in categorytotals:
      for c in allcat:
        if categorytotals[per].get(c) is None:
          categorytotals[per][c] = 0
          categorycount[per][c] = 0
        
    print("ALL CATEGORIES")
    for ii in categorytotals[firstper]:
      if ii is not None:
        print("{:>25}".format(ii[0:24]),end="")
        for per in data:
          print("{:>4}".format(categorycount[per][ii]),end="")
          print("{:>7}".format(categorytotals[per][ii]),end="")
        print("")

    #print("{:>25}  {:>6}".format("Spending total", spendingtotal))
    
    return categorytotals



  def fixcategories(self, data, upcategorydict):
    print("FIX CATEGORIES")
    upvendordict = {}
    for cat in upcategorydict:
      for ii in upcategorydict[cat]:
        upvendordict[ii] = cat
    c = 0
    for x in data:
      att = x["attributes"]
      rel = x["relationships"]
      amount = att["amount"]["valueInBaseUnits"]
      parcat = rel["parentCategory"]["data"]
      notTransfer = rel["transferAccount"]["data"] is None
      lookup = upvendordict.get(att["description"])
      if (parcat is None) and notTransfer and not(lookup=="income"):
        self.tryfixcat(x, lookup)
        c = c + 1
    if c == 0:
      print("All transactions categorised, nothing to do.")

  def tryfixcat(self, x, lookup):
    att = x["attributes"]
    print(att["createdAt"][0:10], att["description"], att["amount"]["value"])
    if (lookup is not None):
      self.patchcat(x["id"], lookup)
    

  def stateload(self):
    filepath = CACHE_DIR + "/_upstate.pickle"
    if not os.path.isdir(CACHE_DIR):
      os.makedirs(CACHE_DIR)
    if os.path.isfile(filepath):
      with open(filepath, 'rb') as file:
        data = pickle.load(file)
# print("UP STATE loaded. Last run: " + data["lastrun"].isoformat())
    else:
      data = {"lastrun": self.now - timedelta(days=DEFAULT_DAYS)}
      print("UP STATE not exists. Setting proxy last run: " +
            data["lastrun"].isoformat())
    self.state = data

  def statestore(self):
    self.state["lastrun"] = self.now
    with open(CACHE_DIR + "/_upstate.pickle", 'wb') as file:
      pickle.dump(self.state, file, pickle.HIGHEST_PROTOCOL)
    # print('UP STATE stored. Setting new last run: ' + self.state["lastrun"].isoformat())

