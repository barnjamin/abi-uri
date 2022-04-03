Algorand ABI URI
=================


It would be convenient to handle scanning a QR code that encodes some application call


This is just a first stab at defining one and how we might parse it out.

Currently just the following have been tried:
```py
    uris = [
        "algorand-abi://123/repeat_message?message={string:hello}&times={uint16:3}",
        "algorand-abi://123/drop_asset?id={asset:456}",
    ]
```

Something like this:

```
scheme://app-id/method-name?arg-name={arg-type:arg-value}
```

It does _not_ yet handle:

    - Other transaction fields specified as parameters (note, valid rounds, etc..)
    - Transaction Reference type arguments
    - Allowing modifiable fields. You could imagine providing a range of values or set of values the signer may choose from.
