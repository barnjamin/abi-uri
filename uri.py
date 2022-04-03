import string
from algosdk.account import generate_account
from algosdk.future import transaction
from algosdk import abi, atomic_transaction_composer as atc
from typing import List, Union
from urllib.parse import urlparse, parse_qsl, parse_qs
import json


class URIMethodArg:

    type: abi.Argument
    name: string
    value: Union[str, int]

    def __init__(self, name: str, val: str):
        self.name = name

        # should only be 2 bits, type && value
        (t, v) = val.strip("{}").split(":")

        self.type = abi.Argument(t)

        if self.type is abi.ABITransactionType:
            raise Exception("Unsupported abi type: {}".format(t))
        elif type(self.type.type) is abi.ABIReferenceType:
            self.value = int(v)
        else:
            if type(self.type.type) is abi.UintType:
                self.value = int(v)
            else:
                self.value = v


class ABIUri:

    app_id: int
    method: abi.Method
    args: List[URIMethodArg]

    def __init__(self, id, meth, args):
        self.app_id = id
        self.method = meth
        self.args = args

    @staticmethod
    def decode(uri: str):
        parsed = urlparse(uri)

        app_id = parsed.netloc

        path_chunks = parsed.path.split("/")[1:]
        method_name = path_chunks[0]

        query_params = parse_qs(parsed.query)
        args = [URIMethodArg(k, val) for k, v in query_params.items() for val in v]

        method = abi.Method(method_name, [a.type for a in args], abi.Returns("void"))

        return ABIUri(int(app_id), method, args)

    def generate_transaction(self, sp, sender, signer):
        comp = atc.AtomicTransactionComposer()

        foreign_assets = []
        foreign_apps = []
        foreign_accts = []
        values = []
        for a in self.args:
            if a.type is abi.ABIReferenceType:
                if a.type == abi.ABIReferenceType.ACCOUNT:
                    values.append(len(foreign_apps) + 1)
                    foreign_accts.append(a.value)
                elif a.type == abi.ABIReferenceType.ASSET:
                    values.append(len(foreign_apps))
                    foreign_assets.append(a.value)
                else:
                    values.append(len(foreign_apps) + 1)
                    foreign_apps.append(a.value)
            else:
                values.append(a.value)

        comp.add_method_call(
            self.app_id,
            self.method,
            sender,
            sp,
            signer,
            values,
            foreign_apps=foreign_apps,
            foreign_assets=foreign_assets,
            accounts=foreign_accts,
        )

        return comp.build_group()[0].txn

    def encode(self):
        return f"algorand-abi://{self.app_id}/{self.method.name}?" + "&".join(
            [f"{arg.name}={{{arg.type.type}:{arg.value}}}" for arg in self.args]
        )


class URITransactionGroup():
    version: string
    transactions: List[ABIUri]

    def __init__(self, version, transactions):
        self.version = version
        self.transactions = transactions

    def encode(self):
        return json.dumps({
            "version":self.version,
            "transactions":[t.encode() for t in self.transactions]
        })



if __name__ == "__main__":


    uris = [
        "algorand-abi://123/repeat_message?message={string:hello}&times={uint16:3}",
        "algorand-abi://123/sell?id={asset:456}",
    ]

    txn_uris = []
    for uri in uris:
        decoded_uri = ABIUri.decode(uri)

        (sk, pk) = generate_account()
        signer = atc.AccountTransactionSigner(sk)
        sp = transaction.SuggestedParams(0, 0, 0, "")
        txn = decoded_uri.generate_transaction(sp, pk, signer)

        txn_uris.append(decoded_uri)

    utg = URITransactionGroup("1.0", txn_uris)
    print(utg.encode())
