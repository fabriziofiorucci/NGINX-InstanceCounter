import flask
from flask import Flask, jsonify, abort, make_response, request, Response
import os
import sys
import ssl
import json
import sched,time,datetime
import requests
import time
import threading
import smtplib
import urllib3.exceptions
import base64
import pandas as pd
from io import BytesIO
from requests import Request, Session
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from email.message import EmailMessage

import cveDB

this = sys.modules[__name__]

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Hardware platform types, names and SKU mappings
# https://support.f5.com/csp/article/K4309
hwPlatforms = {
  "D110": "7250|F5-BIG-7250",
  "D113": "10200|F5-BIG-10200",
  "C113": "4200|F5-BIG-4200",
  "D116": "I15800|F5-BIG-I15800",
  "C124": "I11800|F5-BIG-I11800-DS",
  "C123": "I11800|F5-BIG-I11800",
  "    ": "I10800|F5-BIG-I10800-D",
  "C116": "I10800|F5-BIG-I10800",
  "C126": "I7820-DF|F5-BIG-I7820-DF",
  "    ": "I7800|F5-BIG-I7800-D",
  "C118": "I7800|F5-BIG-I7800",
  "C125": "I5820-DF|F5-BIG-I5820-DF",
  "C119": "I5800|F5-BIG-I5800",
  "C115": "I4800|F5-BIG-I4800",
  "C117": "I2800|F5-BIG-I2800",
  "    ": "C4800|F5-VPR-C4800-DCN",
  "A109": "B2100|F5-VPR-B2100",
  "A113": "B2150|F5-VPR-B2150",
  "A112": "B2250|F5-VPR-B2250",
  "A114": "B4450|F5-VPR-B4450N",
  "F100": "C2400|F5-VPR-C2400-AC",
  "F101": "C2400|F5-VPR-C2400-AC",
  "    ": "C2400|F5-VPR-C2400-ACT",
  "J102": "C4480|F5-VPR-C4480-AC",
  "    ": "C4480|F5-VPR-C4480-DCN",
  "S100": "C4800|F5-VPR-C4800-AC",
  "S101": "C4800|F5-VPR-C4800-AC",
  "Z100": "VE|F5-VE",
  "Z101": "VE-VCMP|F5-VE-VCMP"
}

# TMOS modules SKU
swModules = {
  "gtm": "DNS",
  "sslo": "SSLO",
  "apm": "APM",
  "cgnat": "CGNAT",
  "ltm": "LTM",
  "avr": "",
  "fps": "",
  "dos": "",
  "lc": "",
  "pem": "PEM",
  "urldb": "",
  "swg": "",
  "asm": "AWF",
  "afm": "AFM",
  "ilx": ""
}

this.bigiq_fqdn=''
this.bigiq_username=''
this.bigiq_password=''
this.bigiq_proxy={}

# Module initialization
def init(fqdn,username,password,proxy,nistApiKey):
  this.bigiq_fqdn=fqdn
  this.bigiq_username=username
  this.bigiq_password=password
  this.bigiq_proxy=proxy

  cveDB.init(nistApiKey=nistApiKey,proxy=proxy)


# Thread for scheduled inventory generation
def scheduledInventory():
  while True:
    # Starts inventory generation task
    # https://clouddocs.f5.com/products/big-iq/mgmt-api/v8.1.0/HowToSamples/bigiq_public_api_wf/t_export_device_inventory.html?highlight=inventory
    print(datetime.datetime.now(),"Requesting BIG-IQ inventory refresh")
    res,body = bigIQcallRESTURI(method = "POST", uri = "/mgmt/cm/device/tasks/device-inventory", body = {'devicesQueryUri': 'https://localhost/mgmt/shared/resolver/device-groups/cm-bigip-allBigIpDevices/devices'} )

    time.sleep(86400)


# Reporting
def xlsReport(instancesJson):
  iJson=json.loads(instancesJson)

  #print("-- Importing JSON")
  f5AllDetails = pd.DataFrame(iJson['details'])

  #print("-- Analyzing CVE")
  f5AllCVE = pd.DataFrame()
  for cveArray in f5AllDetails['CVE']:
    for cve in cveArray[0]:
      cveInfo=cveArray[0][cve]
      f5AllCVE=f5AllCVE.append(cveInfo,ignore_index=True)

  f5AllCVESummary=f5AllCVE.drop_duplicates()

  f5allCVECritical=f5AllCVESummary[f5AllCVESummary['baseSeverity'] == 'CRITICAL'].sort_values(by=['baseScore','exploitabilityScore'],ascending=False)
  f5allCVECritical = f5allCVECritical[['id', 'url', 'baseSeverity', 'baseScore', 'exploitabilityScore', 'description']]
  f5allCVEHigh=f5AllCVESummary[f5AllCVESummary['baseSeverity'] == 'HIGH'].sort_values(by=['baseScore','exploitabilityScore'],ascending=False)
  f5allCVEHigh = f5allCVEHigh[['id', 'url', 'baseSeverity', 'baseScore', 'exploitabilityScore', 'description']]
  f5allCVEMedium=f5AllCVESummary[f5AllCVESummary['baseSeverity'] == 'MEDIUM'].sort_values(by=['baseScore','exploitabilityScore'],ascending=False)
  f5allCVEMedium = f5allCVEMedium[['id', 'url', 'baseSeverity', 'baseScore', 'exploitabilityScore', 'description']]
  f5allCVELow=f5AllCVESummary[f5AllCVESummary['baseSeverity'] == 'LOW'].sort_values(by=['baseScore','exploitabilityScore'],ascending=False)
  f5allCVELow = f5allCVELow[['id', 'url', 'baseSeverity', 'baseScore', 'exploitabilityScore', 'description']]

  #print("-- Analyzing TMOS releases")
  allVersionSummary=pd.DataFrame(f5AllDetails.groupby(['version'])['hostname'].count()).rename(columns={'hostname':'count'})

  #print("-- Analyzing hardware devices")
  f5Hardware = f5AllDetails[f5AllDetails['isVirtual'] == 'False'].filter(['hostname','platformMarketingName'])
  f5Hardware = pd.DataFrame(f5Hardware.groupby(['platformMarketingName'])['hostname'].count()).rename(columns={'hostname':'count'})

  #print("-- Analyzing Virtual Editions")
  f5VE = f5AllDetails[f5AllDetails['isVirtual'] == 'True']

  #print("All devices:",f5AllDetails.shape[0])
  #print("- Hardware :",f5Hardware.shape[0])
  #print("- VE & vCMP:",f5VE.shape[0])
  #print("All CVE    :",f5AllCVE.shape[0])
  #print("- Critical :",f5allCVECritical.shape[0])
  #print("- High     :",f5allCVEHigh.shape[0])
  #print("- Medium   :",f5allCVEMedium.shape[0])
  #print("- Low      :",f5allCVELow.shape[0])

  outputfile = BytesIO()

  Excelwriter = pd.ExcelWriter(outputfile, engine='xlsxwriter')

  # All devices sheet
  f5AllDetails.to_excel(Excelwriter,sheet_name='All devices')


  # Hardware devices sheet
  f5Hardware.to_excel(Excelwriter,sheet_name='Hardware')
  hwWorksheet = Excelwriter.sheets['Hardware']
  hwWorksheet.set_column(0,0,25)
  hwWorksheet.set_column(1,1,10)

  hwWorkbook=Excelwriter.book
  hwWorksheet = Excelwriter.sheets['Hardware']
  hwChart=hwWorkbook.add_chart({'type': 'bar'})
  hwChart.set_title({
    'name': 'Hardware devices summary',
    'overlay': False
  })
  hwChart.add_series({
    'categories': '=Hardware!$A$2:$A$'+str(f5Hardware.shape[0]+1),
    'values': '=Hardware!$B$2:$B$'+str(f5Hardware.shape[0]+1),
    'fill': {'color': 'blue'}
  })
  hwChart.set_y_axis({
    'major_gridlines': {
      'visible': True,
      'line': {'width': .5, 'dash_type': 'dash'}
    },
  })
  hwChart.set_legend({'position': 'none'})
  hwWorksheet.insert_chart('F2', hwChart)


  # TMOS sheet
  allVersionSummary.to_excel(Excelwriter,sheet_name='TMOS')

  tmosWorkbook=Excelwriter.book
  tmosWorksheet = Excelwriter.sheets['TMOS']
  chart=tmosWorkbook.add_chart({'type': 'bar'})
  chart.set_title({
    'name': 'TMOS versions summary',
    'overlay': False
  })
  chart.add_series({
    'categories': '=TMOS!$A$2:$A$'+str(allVersionSummary.shape[0]+1),
    'values': '=TMOS!$B$2:$B$'+str(allVersionSummary.shape[0]+1),
    'fill': {'color': 'blue'}
  })
  chart.set_y_axis({
    'major_gridlines': {
      'visible': True,
      'line': {'width': .5, 'dash_type': 'dash'}
    },
  })
  chart.set_legend({'position': 'none'})
  tmosWorksheet.insert_chart('F2', chart)

  # CVE sheet
  f5allCVECriticalStyled = (f5allCVECritical.style.applymap(lambda v: 'background-color: %s' % 'red' if v == 'CRITICAL' else ''))
  f5allCVECriticalStyled.to_excel(Excelwriter,sheet_name='CVE')

  f5allCVEHighStyled = (f5allCVEHigh.style.applymap(lambda v: 'background-color: %s' % 'orange' if v == 'HIGH' else ''))
  f5allCVEHighStyled.to_excel(Excelwriter, sheet_name='CVE',startrow=len(f5allCVECritical)+1,header=False)

  f5allCVEMediumStyled = (f5allCVEMedium.style.applymap(lambda v: 'background-color: %s' % 'yellow' if v == 'MEDIUM' else ''))
  f5allCVEMediumStyled.to_excel(Excelwriter,sheet_name='CVE',startrow=len(f5allCVECritical)+len(f5allCVEHigh)+1,header=False)

  f5allCVELowStyled = (f5allCVELow.style.applymap(lambda v: 'background-color: %s' % 'green' if v == 'LOW' else ''))
  f5allCVELowStyled.to_excel(Excelwriter,sheet_name='CVE',startrow=len(f5allCVECritical)+len(f5allCVEHigh)+len(f5allCVEMedium)+1,header=False)

  cveWorksheet = Excelwriter.sheets['CVE']
  cveWorksheet.set_column(1,1,20)
  cveWorksheet.set_column(2,2,50)
  cveWorksheet.set_column(3,3,15)
  cveWorksheet.set_column(4,4,11)
  cveWorksheet.set_column(5,5,22)
  cveWorksheet.set_column(6,6,128)

  Excelwriter.close()
  outputfile.seek(0)
  #Excelwriter.save()

  return outputfile


### BIG-IQ REST API

# Returns BIG-IP devices managed by BIG-IQ
def bigIQInstances():
  return bigIQcallRESTURI(method = "GET",uri = "/mgmt/shared/resolver/device-groups/cm-bigip-allBigIpDevices/devices",body = "")


# Returns details for a given BIG-IP device
def bigIQInstanceDetails(instanceUUID):
  return bigIQcallRESTURI(method = "GET",uri = "/mgmt/cm/system/machineid-resolver/"+instanceUUID, body = "")


# Returns modules provisioning status details for BIG-IP devices managed by BIG-IQ
def bigIQInstanceProvisioning():
  return bigIQcallRESTURI(method = "GET",uri = "/mgmt/cm/shared/current-config/sys/provision", body ="")


# Returns the most recent inventory for BIG-IP devices managed by BIG-IQ
def bigIQgetInventory():
  # Gets the latest available inventory
  # The "resultsReference" field contains the URL to fetch license/serial number information
  res,body = bigIQcallRESTURI(method = "GET", uri = "/mgmt/cm/device/tasks/device-inventory", body = "" )
  if res != 200:
    return res,body
  else:
    latestUpdate=0
    latestResultsReference=''
    for item in body['items']:
      if item['lastUpdateMicros'] > latestUpdate:
        # "resultsReference": {
        #   "link": "https://localhost/mgmt/cm/device/reports/device-inventory/8982ed9f-1870-4483-96c2-9fb024a2a5b6/results",
        #   "isSubcollection": true
        # }
        latestResultsReference = item['resultsReference']['link'].split('/')[8]
        latestUpdate = item['lastUpdateMicros']

    if latestUpdate == 0:
       return 204,'{}'

    res,body = bigIQcallRESTURI(method = "GET", uri = "/mgmt/cm/device/reports/device-inventory/"+latestResultsReference+"/results", body = "" )

    return res,body


# Invokes the given BIG-IQ REST API method
# The uri must start with '/'
def bigIQcallRESTURI(method,uri,body):
  # Get authorization token
  authRes = requests.request("POST", this.bigiq_fqdn+"/mgmt/shared/authn/login", json = {'username': this.bigiq_username, 'password': this.bigiq_password}, verify=False, proxies=this.bigiq_proxy)

  if authRes.status_code != 200:
    return authRes.status_code,authRes.json()
  authToken = authRes.json()['token']['token']

  # Invokes the BIG-IQ REST API method
  res = requests.request(method, this.bigiq_fqdn+uri, headers = { 'X-F5-Auth-Token': authToken }, json = body, verify=False, proxies=this.bigiq_proxy)

  data = {}
  if res.status_code == 200 or res.status_code == 202:
    if res.content != '':
      data = res.json()

  return res.status_code,data


### BIG-IQ query functions

# Returns NGINX OSS/Plus instances managed by BIG-IQ in JSON format
def bigIqInventory(mode):

  status,details = bigIQInstances()
  if status != 200:
    return make_response(jsonify(details), status)

  output=''

  if mode == 'JSON':
    output = ''
    firstLoop = True

    # Gets TMOS modules provisioning state for all devices
    rcode,provisioningDetails = bigIQInstanceProvisioning()
    rcode2,inventoryDetails = bigIQgetInventory()

    hwSKUGrandTotals={}
    swSKUGrandTotals={}

    for item in details['items']:
      if mode == 'JSON':
        # Gets TMOS registration key and serial number for the current BIG-IP device
        inventoryData = '"inventoryTimestamp":"'+str(inventoryDetails['lastUpdateMicros']//1000)+'",'

        platformType=''

        if rcode2 == 204:
          inventoryData = inventoryData + '"inventoryStatus":"partial",'
        else:
          machineIdFound=False
          for invDevice in inventoryDetails['items']:
            if invDevice['infoState']['machineId'] == item['machineId']:
              machineIdFound=True
              if "errors" in invDevice['infoState']:
                # BIG-IP unreachable, inventory incomplete
                inventoryData = inventoryData + '"inventoryStatus":"partial",'
              else:
                # Get platform name and SKU
                platformCode=invDevice['infoState']['platform']
                platformInsights=''
                if platformCode in hwPlatforms:
                  platformDetails=hwPlatforms[platformCode]
                  platformType=platformDetails.split('|')[0]
                  platformSKU=platformDetails.split('|')[1]

                  if platformSKU in hwSKUGrandTotals:
                    hwSKUGrandTotals[platformSKU] += 1
                  else:
                    hwSKUGrandTotals[platformSKU] = 1

                  platformInsights=',"type":"'+platformType+'","sku":"'+platformSKU+'"'

                inventoryData += '"inventoryStatus":"full","platform":{'+ \
                  '"code":"'+platformCode+'"'+platformInsights+'},'+ \
                  '"registrationKey":"'+invDevice['infoState']['license']['registrationKey']+ \
                  '","chassisSerialNumber":"'+invDevice['infoState']['chassisSerialNumber'].strip()+'",'

                if 'licenseEndDateTime' in invDevice['infoState']['license']:
                  inventoryData += '"licenseEndDateTime":"'+invDevice['infoState']['license']['licenseEndDateTime']+'",'

          if machineIdFound == False:
            inventoryData = inventoryData + '"inventoryStatus":"partial",'

        # Gets TMOS modules provisioning for the current BIG-IP device
        # https://support.f5.com/csp/article/K4309
        provModules = ''
        foundCVEs={}
        pFirstLoop = True
        for prov in provisioningDetails['items']:
          if prov['deviceReference']['machineId'] == item['machineId']:
            if pFirstLoop == True:
              pFirstLoop = False
            else:
              provModules+=','

            # Retrieving relevant SKUs and platform types
            moduleProvisioningLevel=''

            if prov['name'] in swModules:
              moduleName = swModules[prov['name']]
            else:
              moduleName = ''

            if platformType == '' or moduleName == '':
              moduleSKU = ''
            else:
              moduleSKU = "H-"+platformType+"-"+moduleName
              moduleProvisioningLevel=prov['level']

              if moduleProvisioningLevel != 'none':
                # CVE tracking
                allCVE=cveDB.getF5(product=prov['name'],version=item['version'])
                foundCVEs.update(allCVE)

                if moduleSKU in swSKUGrandTotals:
                  swSKUGrandTotals[moduleSKU] += 1
                else:
                  swSKUGrandTotals[moduleSKU] = 1

            provModules += '{"module":"'+prov['name']+'","level":"'+moduleProvisioningLevel+'","sku":"'+moduleSKU+'"}'

        # Gets TMOS licensed modules for the current BIG-IP device
        retcode,instanceDetails = bigIQInstanceDetails(item['machineId'])

        if retcode == 200:
          if instanceDetails != '':
            if firstLoop == True :
              firstLoop = False
            else:
              output+=','

            licensedModules = instanceDetails['properties']['cm:gui:module']

            platformMarketingName=''
            if 'platformMarketingName' in item:
              platformMarketingName=item['platformMarketingName']

            output += '{"hostname":"'+item['hostname']+'","address":"'+item['address']+'","product":"'+item['product']+'","version":"'+item['version']+'","edition":"'+ \
              item['edition']+'","build":"'+item['build']+'","isVirtual":"'+str(item['isVirtual'])+'","isClustered":"'+str(item['isClustered'])+ \
              '","platformMarketingName":"'+platformMarketingName+'","restFrameworkVersion":"'+ \
              item['restFrameworkVersion']+'",'+inventoryData+'"licensedModules":'+str(licensedModules).replace('\'','"')+ \
              ',"provisionedModules":['+provModules+'],"CVE":['+json.dumps(foundCVEs)+']}'

    output = '{ "instances": [{ "bigip":"'+str(len(details['items']))+'",'+ \
      '"hwTotals":['+json.dumps(hwSKUGrandTotals)+'],' \
      '"swTotals":['+json.dumps(swSKUGrandTotals)+ \
      ']}], "details": [' + output + ']}'
  elif mode == 'PROMETHEUS' or mode == 'PUSHGATEWAY':
    if mode == 'PROMETHEUS':
      output = '# HELP bigip_online_instances Online BIG-IP instances\n'
      output = output + '# TYPE bigip_online_instances gauge\n'

    output = output + 'bigip_online_instances{instanceType="BIG-IQ",bigiq_url="'+bigiq_fqdn+'"} '+str(len(details['items']))+'\n'

  return output