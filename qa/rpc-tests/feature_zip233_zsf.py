#!/usr/bin/env python3
# Copyright (c) 2024 The Zcash developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://www.opensource.org/licenses/mit-license.php .

from test_framework.test_framework import BitcoinTestFramework
from test_framework.authproxy import JSONRPCException
from test_framework.util import (
    assert_equal,
    assert_false,
    assert_raises_message,
    connect_nodes_bi,
    start_nodes,
    sync_mempools,
    nuparams,
    NU5_BRANCH_ID,
    ZFUTURE_BRANCH_ID,
)
import time

from decimal import Decimal

class Zip233ZsfTest(BitcoinTestFramework):

    def __init__(self):
        super().__init__()
        self.cache_behavior = 'clean'
        self.num_nodes = 2

    def setup_network(self, split = False):
        assert_false(split, False)
        self.is_network_split = False
        self.nodes = start_nodes(self.num_nodes, self.options.tmpdir, extra_args=[[
            nuparams(NU5_BRANCH_ID, 1),
            nuparams(ZFUTURE_BRANCH_ID, 103),
            '-nurejectoldversions=false',
            '-allowdeprecated=getnewaddress'
        ]] * self.num_nodes)
        connect_nodes_bi(self.nodes, 0, 1)
        self.sync_all()

    def run_test(self):
        BLOCK_REWARD = Decimal("6.25")
        COINBASE_MATURATION_BLOCK_COUNT = 100
        TRANSACTION_FEE = Decimal("0.0001")

        alice, bob = self.nodes

        # Activate all upgrades up to and including NU5
        alice.generate(1)

        # Wait for our coinbase to mature and become spendable
        alice.generate(COINBASE_MATURATION_BLOCK_COUNT)

        block_height = 1 + COINBASE_MATURATION_BLOCK_COUNT
        self.sync_all()

        expected_chain_value = BLOCK_REWARD * block_height
        assert_equal(
            alice.getblockchaininfo()["chainSupply"]["chainValue"],
            expected_chain_value
        )
        assert_equal(
            bob.getblockchaininfo()["chainSupply"]["chainValue"],
            expected_chain_value
        )

        # Only the first block's coinbase has reached maturity
        assert_equal(alice.getbalance(), BLOCK_REWARD)
        assert_equal(bob.getbalance(), 0)

        bob_address = bob.getnewaddress()
        send_amount = Decimal("1.23")
        zsf_deposit_amount = Decimal("1.11")
        sendtoaddress_args = [
            bob_address,
            send_amount,
            "",
            "",
            False,
            zsf_deposit_amount
        ]

        assert_raises_message(
            JSONRPCException,
            "ZSF deposit is not supported at this block height.",
            alice.sendtoaddress,
            *sendtoaddress_args
        )

        # Activate upgrade that introduces ZSF deposit support
        alice.generate(1)
        block_height += 1

        # And now the same RPC call should succeed
        alice.sendtoaddress(*sendtoaddress_args)

        # Using the other node to mine ensures we test transaction serialization
        sync_mempools([alice, bob])
        bob.generate(1)
        block_height += 1
        self.sync_all()

        expected_alice_balance = (
            (BLOCK_REWARD * 3)
            - send_amount
            - zsf_deposit_amount
            - TRANSACTION_FEE
        )
        expected_bob_balance = send_amount

        assert_equal(alice.getbalance(), expected_alice_balance)
        assert_equal(bob.getbalance(), expected_bob_balance)

        expected_chain_value = BLOCK_REWARD * block_height - zsf_deposit_amount
        assert_equal(
            alice.getblockchaininfo()["chainSupply"]["chainValue"],
            expected_chain_value
        )
        assert_equal(
            bob.getblockchaininfo()["chainSupply"]["chainValue"],
            expected_chain_value
        )

        # Try the same using createrawtransaction
        raw_transaction = (
            alice.createrawtransaction(
                [],
                {bob_address: send_amount},
                None,
                None,
                zsf_deposit_amount
            )
        )
        funded_transaction = alice.fundrawtransaction(raw_transaction)
        signed_transaction = alice.signrawtransaction(funded_transaction["hex"])
        transaction_hash = alice.sendrawtransaction(signed_transaction["hex"])

        assert_equal(alice.decoderawtransaction(raw_transaction)["zsfDeposit"], zsf_deposit_amount)
        assert_equal(alice.decoderawtransaction(funded_transaction["hex"])["zsfDeposit"], zsf_deposit_amount)
        assert_equal(alice.decoderawtransaction(signed_transaction["hex"])["zsfDeposit"], zsf_deposit_amount)

        alice.generate(1)
        self.sync_all()

        assert_equal(bob.getrawtransaction(transaction_hash, 1)["zsfDeposit"], zsf_deposit_amount)

        expected_alice_balance += (
            BLOCK_REWARD
            - send_amount
            - zsf_deposit_amount
            - TRANSACTION_FEE
        )
        expected_bob_balance += send_amount

        assert_equal(alice.getbalance(), expected_alice_balance)
        assert_equal(bob.getbalance(), expected_bob_balance)

        expected_chain_value += BLOCK_REWARD - zsf_deposit_amount
        assert_equal(
            alice.getblockchaininfo()["chainSupply"]["chainValue"],
            expected_chain_value
        )
        assert_equal(
            bob.getblockchaininfo()["chainSupply"]["chainValue"],
            expected_chain_value
        )

if __name__ == '__main__':
    Zip233ZsfTest().main()
