targetScope = 'resourceGroup'
param location string = resourceGroup().location
param prefix string = 'nkust-demo'
@minLength(40)
@maxLength(40)
param imageTag string
@secure()
@minLength(32)
param monitoringToken string

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: '${prefix}-env'
}
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: 'nkust${uniqueString(resourceGroup().id)}'
}
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: '${prefix}-pull'
}
var hostname = '${prefix}.${environment.properties.defaultDomain}'
resource web 'Microsoft.App/containerApps@2025-01-01' = {
  name: prefix
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      secrets: [{
        name: 'monitoring-token'
        value: monitoringToken
      }]
      registries: [{
        server: registry.properties.loginServer
        identity: identity.id
      }]
    }
    template: {
      containers: [{
        name: 'web'
        image: '${registry.properties.loginServer}/nkust-demo:${imageTag}'
        resources: {
          cpu: json('0.5')
          memory: '1Gi'
        }
        env: [
          {
            name: 'DEMO_MODE'
            value: '1'
          }
          {
            name: 'APP_BASE_URL'
            value: 'https://${hostname}'
          }
          {
            name: 'MONITORING_TOKEN'
            secretRef: 'monitoring-token'
          }
        ]
        probes: [
          {
            type: 'Startup'
            tcpSocket: { port: 8000 }
            periodSeconds: 5
            failureThreshold: 24
          }
          {
            type: 'Liveness'
            httpGet: {
              path: '/health/live'
              port: 8000
              httpHeaders: [{
                name: 'Host'
                value: hostname
              }]
            }
            periodSeconds: 10
            timeoutSeconds: 5
          }
          {
            type: 'Readiness'
            httpGet: {
              path: '/health/ready'
              port: 8000
              httpHeaders: [{
                name: 'Host'
                value: hostname
              }]
            }
            periodSeconds: 10
            timeoutSeconds: 5
          }
        ]
      }]
      // Ephemeral SQLite demonstration: never scale out or use real mail.
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}
output demoUrl string = 'https://${web.properties.configuration.ingress.fqdn}/demo'
