// ─────────────────────────────────────────────────────────────────────────────
// ⚠ ASSUMED INTERFACE — PLACEHOLDER UNTIL THE INFRA TEAM'S FILE ARRIVES (D9)
//
// Replace wholesale with the infra team's `container-app.bicep`; then adjust the two
// module calls in main.bicep. Never edit a vendored block in a project.
// ─────────────────────────────────────────────────────────────────────────────
//
// One container app inside the SHARED Container Apps Environment (platform tier), running
// one image from the SHARED registry, authenticated with a user-assigned identity that the
// cloud team has granted AcrPull. Secrets come from the use case's Key Vault through the
// same identity. Health probes hit /health (the unversioned operational endpoint).

@description('App name (ca-<slug>-<env>-<service>).')
param name string

@description('Region (must match the environment\'s).')
param location string

@description('Tags.')
param tags object = {}

@description('Resource ID of the shared Container Apps Environment.')
param environmentId string

@description('Resource ID of the user-assigned identity (pulls the image, reads Key Vault).')
param identityId string

@description('Full image reference, e.g. <registry>.azurecr.io/<slug>-api:<tag>.')
param image string

@description('Login server of the shared registry.')
param registryServer string

@description('Port the container listens on.')
param targetPort int

@description('true = reachable from the internet (web); false = internal to the environment (api).')
param externalIngress bool

@description('Plain environment variables: { NAME: "value" }.')
param env object = {}

@description('Env vars backed by Key Vault secrets: { ENV_NAME: "<vaultUri>secrets/<secret-name>" } (URLs, not values).')
param keyVaultEnvRefs object = {}

@description('CPU cores (0.25 steps).')
param cpu string = '0.5'

@description('Memory (Gi).')
param memory string = '1Gi'

@minValue(0)
param minReplicas int = 1

@minValue(1)
param maxReplicas int = 3

@description('Path of the liveness/readiness probe.')
param healthPath string = '/health'

var secretItems = [
  for item in items(keyVaultEnvRefs): {
    name: toLower(replace(item.key, '_', '-'))
    keyVaultUrl: item.value
    identity: identityId
  }
]

var plainEnv = [for item in items(env): { name: item.key, value: item.value }]
var secretEnv = [
  for item in items(keyVaultEnvRefs): { name: item.key, secretRef: toLower(replace(item.key, '_', '-')) }
]

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: externalIngress
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: [{ server: registryServer, identity: identityId }]
      secrets: secretItems
    }
    template: {
      containers: [
        {
          name: 'app'
          image: image
          resources: { cpu: json(cpu), memory: memory }
          env: concat(plainEnv, secretEnv)
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: healthPath, port: targetPort }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: healthPath, port: targetPort }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: { minReplicas: minReplicas, maxReplicas: maxReplicas }
    }
  }
}

output id string = app.id
output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
