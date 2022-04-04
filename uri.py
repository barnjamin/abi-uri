from abc import ABC, abstractmethod, abstractstaticmethod
import string
from algosdk.account import generate_account
from algosdk.future import transaction
from algosdk import abi, atomic_transaction_composer as atc
from typing import List, Union, Dict
from urllib.parse import urlparse, parse_qsl, parse_qs
import json


class URIEncodedTransaction(ABC):
    @abstractstaticmethod
    def decode(uri: string) -> "URIEncodedTransaction":
        pass

    @abstractmethod
    def generate_transaction(self) -> transaction.Transaction:
        pass

    @abstractmethod
    def encode(self) -> str:
        pass


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


class ABIUri(URIEncodedTransaction):

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

    def generate_transaction(self, sp, sender):

        signer = atc.AccountTransactionSigner("")

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


class PaymentURI(URIEncodedTransaction):
    addr: str
    amount: int
    label: str
    asset: int
    note: str
    xnote: str
    other: Dict[str, str]

    def __init__(
        self,
        addr=None,
        amount=None,
        asset=None,
        label=None,
        note=None,
        xnote=None,
        other=None,
    ):
        self.addr = addr
        self.amount = amount
        self.asset = asset
        self.label = label
        self.note = note
        self.xnote = xnote
        self.other = other

    @staticmethod
    def decode(uri: str):
        parsed = urlparse(uri)

        puri = PaymentURI()
        puri.addr = parsed.netloc
        puri.other = {}

        query_params = parse_qs(parsed.query)
        for k, v in query_params.items():
            if k == "amount":
                puri.amount = int(v[0])
            elif k == "asset":
                puri.asset = int(v[0])
            elif k == "label":
                puri.label = v[0]
            elif k == "note":
                puri.note = v[0]
            elif k == "xnote":
                puri.xnote = v[0]
            else:
                puri.other[k] = v[0]

        return puri

    def generate_transaction(self, sp, sender):
        if self.amount == None:
            raise Exception("No amount specified")

        if self.addr == None:
            raise Exception("No receiver specified")

        if self.asset != None:
            return transaction.AssetTransferTxn(
                sender, sp, self.addr, self.amount, self.asset
            )

        return transaction.PaymentTxn(sender, sp, self.addr, self.amount)

    def encode(self):
        args = []
        if self.amount != None:
            args.append(f"amount={self.amount}")
        if self.label != None:
            args.append(f"label={self.label}")
        if self.asset != None:
            args.append(f"asset={self.asset}")
        if self.note != None:
            args.append(f"asset={self.note}")
        if self.xnote != None:
            args.append(f"xnote={self.xnote}")
        if self.other != None:
            for k, v in self.other.items():
                args.append(f"{k}={v}")

        return f"algorand://{self.addr}?{'&'.join(args)}"


class URITransactionGroup:
    version: string
    transactions: List[URIEncodedTransaction]

    def __init__(self, version, transactions):
        self.version = version
        self.transactions = transactions

    def encode(self):
        return json.dumps(
            {
                "version": self.version,
                "transactions": [t.encode() for t in self.transactions],
            }
        )


if __name__ == "__main__":

    uris = [
        "algorand://TMTAD6N22HCS2LKH7677L2KFLT3PAQWY6M4JFQFXQS32ECBFC23F57RYX4?amount=150500000",
        "algorand-abi://123/sell?id={asset:456}",
    ]

    txn_uris = []
    for uri in uris:
        # Decode the URI
        proto = uri.split(":")[0]

        if proto == "algorand-abi":
            decoded_uri = ABIUri.decode(uri)
        else:
            decoded_uri = PaymentURI.decode(uri)

        # Generate a transaction based on the URI
        (sk, pk) = generate_account()
        sp = transaction.SuggestedParams(0, 0, 0, "")
        txn = decoded_uri.generate_transaction(sp, pk)

        # Re-use the ABIUri to populate a transaction group
        txn_uris.append(decoded_uri)

    # Create transaction group using the ABIUri list
    # should be the same as URIs specified above
    utg = URITransactionGroup("1.0", txn_uris)
    print(utg.encode())
