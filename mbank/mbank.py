#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Copyright (c) Adam Strauch
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice,
       this list of conditions and the following disclaimer.
   
    2. Redistributions in binary form must reproduce the above copyright
       notice, this list of conditions and the following disclaimer in the
       documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


#####################################################################
"""

import csv
import requests
import re
import sys
import datetime

class MbankException(Exception): pass

class mBank(object):
    top_url = "https://cz.mbank.eu/top.aspx"
    frames_url = "https://cz.mbank.eu/frames.aspx"
    form_url = "https://cz.mbank.eu/"
    login_url = "https://cz.mbank.eu/logon.aspx"
    transactions_url = "https://cz.mbank.eu/account_oper_list.aspx"
    transactions_csv_url = "https://cz.mbank.eu/printout_oper_list.aspx"
    accounts_url = "https://cz.mbank.eu/accounts_list.aspx"

    def __init__(self, customer, password):
        self.customer = customer
        self.password = password
        self.cookie = ""
        self.data = {}
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Charset": "UTF-8,*;q=0.5",
            "Accept-Encoding": "gzip,deflate,sdch",
            "Accept-Language": "cs,en;q=0.8,en-US;q=0.6",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            #"Content-Length": "664",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "cz.mbank.eu",
            #"Origin": "https://cz.mbank.eu",
            #"Referer": "https://cz.mbank.eu/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/536.5 (KHTML, like Gecko) Chrome/19.0.1084.52 Safari/536.5",
        }
        self.session = requests.session(headers=self.headers)

    def parse_variables(self, request):
        s_event = re.search("id=\"__EVENTVALIDATION\" value=\"([^\"]*)\"", request.text)
        s_seed = re.search("id=\"seed\" value=\"([^\"]*)\"", request.text)
        s_state = re.search("id=\"__STATE\" value=\"([^\"]*)\"", request.text)
        self.data = {
            "eventvalidation": "",
            "seed": "",
            "state": "",
            "date": "",
        }
        try:
            if s_event: self.data["eventvalidation"] = s_event.groups()[0]
            if s_seed: self.data["seed"] = s_seed.groups()[0]
            if s_state: self.data["state"] = s_state.groups()[0]
            self.data["date"] = datetime.datetime.now().strftime("%a %b %d %Y %H:%M:%S GMT +0100 (Central Europe Standard Time)")
            if "set-cookie" in request.headers:
                self.cookie =  " ".join([x for x in request.headers["set-cookie"].split(" ") if "=" in x and "path" not in x and "expires" not in x])
        except IndexError:
            raise MbankException("Bad parsed value")
        return self.data

    def load(self, url, method="get", data={}):
        if method not in ("post", "get"): raise MbankException("Method unknown")
        try:
            if method == "get":
                r = self.session.get(url, verify=True, allow_redirects=False)
            elif method == "post":
                r = self.session.post(url, verify=True, data=data, allow_redirects=False)
        except requests.exceptions.ConnectionError:
            raise MbankException("Connection error")
        return r

    def login(self):
        r_login_page = self.load(self.form_url)
        data = self.parse_variables(r_login_page)
        login_data = {
            "customer": self.customer,
            "password": self.password,
            "localDT": data["date"],
            "__PARAMETERS": "",
            "__VIEWSTATE": "",
            "seed": data["seed"],
            "__STATE": data["state"],
            "__EVENTVALIDATION": data["eventvalidation"],
        }
        r_login = self.load(self.login_url, "post", login_data)
        self.parse_variables(r_login)
        if '<html><head><title>Object moved</title></head><body>' not in r_login.text:
            raise MbankException("Bad login")

    def get_accounts(self):
        if not self.data:
            raise MbankException("Login first!")

        r_accounts = self.load(self.accounts_url, "get")
        self.parse_variables(r_accounts)
        q = "doSubmit\('/account_oper_list\.aspx','','POST','([^']*)',false,false,false,null\);"
        result = re.findall(q, r_accounts.text)
        parms = result[::-2][::-1]
        q = '<p class="Amount"><span id="AccountsGrid[a-zA-Z0-9\_]*">([ ,0-9A-Z]*)</span></p>'
        cashs = re.findall(q, r_accounts.text)
        q = "(670100-[0-9]{10}/6210)"
        accounts = re.findall(q, r_accounts.text)
        if len(accounts) != len(parms) or len(accounts) != len(cashs):
            raise MbankException("Parse error")

        data = {}
        i = 0
        for account in accounts:
            data[account] = {"amount": cashs[i], "parm": parms[i]}
            i+=1
        return data

    def get_transactions_csv(self, account):
        if not self.data:
            raise MbankException("Login first!")

        accounts = self.get_accounts()
        if account not in accounts:
            raise MbankException("Choose right account number")

        form_data = {
            '__PARAMETERS': accounts[account]["parm"],
            '__VIEWSTATE': '',
            "__STATE": self.data["state"],
        }
        r_middlestep = self.load(self.transactions_url, "post", form_data)
        self.parse_variables(r_middlestep)
    
        form_data = {
            '__PARAMETERS': '',
            '__VIEWSTATE': '',
            "__STATE": self.data["state"],
            "__EVENTVALIDATION": self.data["eventvalidation"],
            'rangepanel_group': 'daterange_radio',
            'daterange_from_day': 1,
            'daterange_from_month': 5,
            'daterange_from_year': 2012,
            'daterange_to_day': 24,
            'daterange_to_month': 6,
            'daterange_to_year': 2012,
            'accoperlist_typefilter_group': 'ALL',
            'accoperlist_amountfilter_amountmin': '',
            'accoperlist_amountfilter_amountmax': '',
            'export_oper_history_check': 'on',
            'export_oper_history_format': 'CSV',
        }
        r_csv = self.load(self.transactions_csv_url, "post", form_data)
        return r_csv.text

    def get_transactions(self, account):
        data = self.get_transactions_csv(account)
        lines = []
        write = False
        for line in data.split("\n"):
            if write and line.strip() == "":
                break
            if write:
                lines.append(line.strip())
            if "Popis transakce" in line:
                write = True
        result = []
        for x in lines:
            x = x.split(";")
            date1 = [int(i) for i in x[0].split("-")]
            date2 = [int(i) for i in x[1].split("-")]
            o = {
                "date_realization": datetime.date(date1[2], date1[1], date1[0]),
                "date_accounting": datetime.date(date2[2], date2[1], date2[0]),
                "type": "outcoming" if "ODCHOZ" in x[2].decode("iso-8859-2") else "incoming",
                "price": float(x[-2].replace(" ", "").replace(",", ".")),
                "ss": int(x[-4]) if x[-4] else 0,
                "vs": int(x[-5]) if x[-5] else 0,
                "ks": int(x[-6]) if x[-6] else 0,
            }
            result.append(o)
        return result

def transactions_format(data):
    print "Date".ljust(19),
    print "Type".ljust(10),
    print "SS".ljust(10),
    print "VS".ljust(10),
    print "KS".ljust(10),
    print "Price".ljust(10)
    print "-------------------------------------------------------------------------"
    for trans in data:
        print trans["date_realization"].strftime("%d.%m.%Y").ljust(19),
        print trans["type"].ljust(10),
        print ("%d" % trans["ss"]).ljust(10),
        print ("%d" % trans["vs"]).ljust(10),
        print ("%d" % trans["ks"]).ljust(10),
        print ("%.2f" % trans["price"]).ljust(10)

def main():
    customer = ""
    password = ""
    account = "670100-2206514444/6210"

    mbank = mBank(customer, password)
    mbank.login()
    result = mbank.get_transactions(account)
    transactions_format(result)

if __name__ == "__main__":
    main()
