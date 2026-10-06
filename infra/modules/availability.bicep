// ─────────────────────────────────────────────────────────────────────────────
// Availability webtests (roadmap Phase 5):
//   one STANDARD availability test per public endpoint (the unversioned
//   /health endpoints exist for exactly this), probing from multiple Azure
//   locations, alerting only when several locations fail simultaneously
//   (single-location blips don't page anyone).
// ─────────────────────────────────────────────────────────────────────────────

@description('Base name used in alert resource names.')
param baseName string

@description('Region for the webtest resources (usually the App Insights region).')
param location string

@description('Resource ID of the Application Insights component the tests report into.')
param appInsightsId string

@description('''
Public endpoints to probe: array of { name: string, url: string } — e.g.
{ name: 'web-health', url: 'https://<web-fqdn>/health' }. Empty (default) =
skip — the apps have no public FQDNs until they are deployed.
''')
param webTests array = []

@description('''
Azure webtest probe locations (population IDs). Defaults: East US (Ashburn),
Central US (Chicago), West Europe (Amsterdam), North Europe (Dublin),
Southeast Asia (Singapore). Adjust to your user geography.
''')
param testLocations array = [
  'us-va-ash-azr'
  'us-il-ch1-azr'
  'emea-nl-ams-azr'
  'emea-gb-db3-azr'
  'apac-sg-sin-azr'
]

@description('Alert when at least this many locations fail in the same window.')
param failedLocationCount int = 2

@description('Probe frequency in seconds (300 or 600 or 900).')
param testFrequencySeconds int = 300

@description('Action group the availability alerts notify.')
param actionGroupId string

resource availabilityTests 'Microsoft.Insights/webtests@2022-06-15' = [
  for test in webTests: {
    name: 'webtest-${baseName}-${test.name}'
    location: location
    // The hidden-link tag is REQUIRED — it binds the webtest to the component.
    tags: {
      'hidden-link:${appInsightsId}': 'Resource'
    }
    kind: 'standard'
    properties: {
      SyntheticMonitorId: 'webtest-${baseName}-${test.name}'
      Name: 'webtest-${baseName}-${test.name}'
      Description: 'Standard availability probe for ${test.url}'
      Enabled: true
      Frequency: testFrequencySeconds
      Timeout: 30
      Kind: 'standard'
      RetryEnabled: true
      Locations: map(testLocations, loc => { Id: loc })
      Request: {
        RequestUrl: test.url
        HttpVerb: 'GET'
        ParseDependentRequests: false
      }
      ValidationRules: {
        ExpectedHttpStatusCode: 200
        // /health is probed over HTTPS in real deployments; cert validity is
        // asserted separately by SSLCheck when the URL is https.
        SSLCheck: startsWith(toLower(test.url), 'https://')
      }
    }
  }
]

resource availabilityAlerts 'Microsoft.Insights/metricAlerts@2018-03-01' = [
  for (test, i) in webTests: {
    name: 'alert-${baseName}-${test.name}-availability'
    location: 'global'
    properties: {
      description: '${test.url} failed from ${failedLocationCount}+ locations simultaneously.'
      severity: 1
      enabled: true
      scopes: [
        availabilityTests[i].id
        appInsightsId
      ]
      evaluationFrequency: 'PT1M'
      windowSize: 'PT5M'
      criteria: {
        'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
        webTestId: availabilityTests[i].id
        componentId: appInsightsId
        failedLocationCount: failedLocationCount
      }
      autoMitigate: true
      actions: [
        {
          actionGroupId: actionGroupId
        }
      ]
    }
  }
]
