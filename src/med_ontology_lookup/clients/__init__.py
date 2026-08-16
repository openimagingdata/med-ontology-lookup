"""HTTP clients for BioPortal and UMLS."""

from med_ontology_lookup.clients.bioportal import BioPortalClient
from med_ontology_lookup.clients.umls import UMLSClient

__all__ = ["BioPortalClient", "UMLSClient"]
