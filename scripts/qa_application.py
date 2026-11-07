"""Isolated browser-test factory: real providers, desktop mutations disabled."""
from app.main import create_app as production_app
from app.permissions import ApprovalStore


def refuse_mutation(argv):
    return {'ok':False,'message':'Desktop mutations are disabled in this isolated QA process'}

class NoMutationApprovalStore(ApprovalStore):
    def __init__(self,path,policy):
        super().__init__(path,policy,executor=refuse_mutation)


def create_app():
    import app.main
    app.main.ApprovalStore=NoMutationApprovalStore
    return production_app()
