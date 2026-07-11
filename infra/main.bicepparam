using './main.bicep'

param baseName = 'ringo'
param location = 'australiaeast'
param searchSku = 'basic'
param openAiSku = 'S0'
param speechSku = 'S0'
param orchestratorCapacity = 30
param visionCapacity = 10
param plannerCapacity = 10
param embeddingCapacity = 30
param searchIndexName = 'ringo-memory'
param servicePrincipalObjectId = '8d0ae25c-7caa-4029-bbad-ce33d0361e8d'
