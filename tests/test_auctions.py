# This file is part of Maker Keeper Framework.
#
# Copyright (C) 2018 reverendus, bargst
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import pytest
from datetime import datetime
from typing import Optional
from web3 import Web3

from pymaker import Address
from pymaker.approval import directly, hope_directly
from pymaker.auctions import Flipper, Flapper, Flopper
from pymaker.deployment import DssDeployment
from pymaker.dss import Collateral, Urn
from pymaker.numeric import Wad, Ray, Rad
from tests.test_dss import TestVat, TestCat, wrap_eth, mint_mkr, set_collateral_price, wait


class TestFlipper:
    @pytest.fixture(scope="session")
    def collateral(self, mcd: DssDeployment) -> Collateral:
        return mcd.collaterals[0]

    @pytest.fixture(scope="session")
    def flipper(self, collateral, deployment_address) -> Flipper:
        return collateral.flipper

    @staticmethod
    def tend(flipper: Flipper, id: int, address: Address, lot: Wad, bid: Rad):
        assert (isinstance(flipper, Flipper))
        assert (isinstance(id, int))
        assert (isinstance(lot, Wad))
        assert (isinstance(bid, Rad))

        current_bid = flipper.bids(id)
        assert current_bid.guy != Address("0x0000000000000000000000000000000000000000")
        assert current_bid.tic > datetime.now().timestamp() or current_bid.tic == 0
        assert current_bid.end > datetime.now().timestamp()

        assert lot == current_bid.lot
        assert bid <= current_bid.tab
        assert bid > current_bid.bid
        assert (bid >= Rad(flipper.beg()) * current_bid.bid) or (bid == current_bid.tab)

        assert flipper.tend(id, lot, bid).transact(from_address=address)

    @staticmethod
    def dent(flipper: Flipper, id: int, address: Address, lot: Wad, bid: Rad):
        assert (isinstance(flipper, Flipper))
        assert (isinstance(id, int))
        assert (isinstance(lot, Wad))
        assert (isinstance(bid, Rad))

        current_bid = flipper.bids(id)
        assert current_bid.guy != Address("0x0000000000000000000000000000000000000000")
        assert current_bid.tic > datetime.now().timestamp() or current_bid.tic == 0
        assert current_bid.end > datetime.now().timestamp()

        assert bid == current_bid.bid
        assert bid == current_bid.tab
        assert lot < current_bid.lot
        assert (flipper.beg() * Ray(lot)) <= Ray(current_bid.lot)

        assert flipper.dent(id, lot, bid).transact(from_address=address)

    def test_getters(self, mcd, flipper):
        assert flipper.vat() == mcd.vat.address
        assert flipper.beg() == Ray.from_number(1.05)
        assert flipper.ttl() > 0
        assert flipper.tau() > flipper.ttl()
        assert flipper.kicks() >= 0

    def test_scenario(self, web3, mcd, collateral, flipper, our_address, other_address, deployment_address):
        # Create a CDP
        collateral = mcd.collaterals[0]
        kicks_before = flipper.kicks()
        ilk = collateral.ilk
        wrap_eth(mcd, deployment_address, Wad.from_number(1))
        assert collateral.adapter.join(deployment_address, Wad.from_number(1)).transact(
            from_address=deployment_address)
        TestVat.frob(mcd, collateral, deployment_address, dink=Wad.from_number(1), dart=Wad(0))
        max_dart = TestVat.max_dart(mcd, collateral, deployment_address) - Wad(1)
        TestVat.frob(mcd, collateral, deployment_address, dink=Wad(0), dart=max_dart)

        # Mint and withdraw all the Dai
        mcd.dai_adapter.approve(approval_function=hope_directly(), vat=mcd.vat.address, from_address=deployment_address)
        assert mcd.dai_adapter.exit(deployment_address, max_dart).transact(from_address=deployment_address)
        assert mcd.dai.balance_of(deployment_address) == max_dart
        assert mcd.vat.dai(deployment_address) == Rad(0)

        # Undercollateralize the CDP
        to_price = Wad(Web3.toInt(collateral.pip.read())) / Wad.from_number(2)
        set_collateral_price(mcd, collateral, to_price)
        urn = mcd.vat.urn(collateral.ilk, deployment_address)
        ilk = mcd.vat.ilk(ilk.name)
        assert ilk.rate is not None
        assert ilk.spot is not None
        safe = Ray(urn.art) * mcd.vat.ilk(ilk.name).rate <= Ray(urn.ink) * ilk.spot
        assert not safe
        assert len(flipper.active_auctions()) == 0

        # Bite the CDP, which moves debt to the vow and kicks the flipper
        urn = mcd.vat.urn(collateral.ilk, deployment_address)
        assert urn.ink > Wad(0)
        lot = min(urn.ink, mcd.cat.lump(ilk))  # Wad
        art = min(urn.art, (lot * urn.art) / urn.ink)  # Wad
        tab = art * ilk.rate  # Wad
        assert tab == max_dart
        TestCat.simulate_bite(mcd, collateral, deployment_address)
        assert mcd.cat.bite(collateral.ilk, Urn(deployment_address)).transact()
        urn = mcd.vat.urn(collateral.ilk, deployment_address)
        # Check vat, vow, and cat
        assert urn.ink == Wad(0)
        assert urn.art == max_dart - art
        assert mcd.vat.vice() > Rad(0)
        assert mcd.vow.sin() == Rad(tab)
        bites = mcd.cat.past_bite(10)
        assert len(bites) == 1
        last_bite = bites[0]
        assert last_bite.tab > Rad(0)
        # Check the flipper
        assert flipper.kicks() == kicks_before + 1
        current_bid = flipper.bids(1)
        assert isinstance(current_bid, Flipper.Bid)
        assert current_bid.lot > Wad(0)
        assert current_bid.tab > Rad(0)
        assert current_bid.bid == Rad(0)
        # Cat doesn't incorporate the liquidation penalty (chop), but the kicker includes it.
        # Awaiting word from @dc why this is so.
        # assert last_bite.tab == current_bid.tab
        assert len(flipper.active_auctions()) == 1

        # Test the _tend_ phase of the auction
        eth_required = Wad(current_bid.tab / Rad(ilk.spot)) * Wad.from_number(1.1)
        wrap_eth(mcd, other_address, eth_required)
        assert collateral.gem.balance_of(other_address)  >= eth_required
        collateral.gem.approve(collateral.adapter.address)
        assert collateral.adapter.join(other_address, eth_required).transact(from_address=other_address)
        flipper.approve(approval_function=hope_directly(), from_address=other_address)
        assert mcd.vat.can(other_address, flipper.address)
        # Add Wad(1) to counter rounding error converting tab from Rad to Wad
        TestVat.frob(mcd, collateral, other_address, dink=eth_required, dart=Wad(current_bid.tab) + Wad(1))
        urn = mcd.vat.urn(collateral.ilk, other_address)
        assert Rad(urn.art) >= current_bid.tab
        # Bid the tab to instantly transition to dent stage
        TestFlipper.tend(flipper, 1, other_address, current_bid.lot, current_bid.tab)
        current_bid = flipper.bids(1)
        assert current_bid.guy == other_address
        assert current_bid.bid == current_bid.tab

        # Test the _dent_ phase of the auction
        wrap_eth(mcd, our_address, eth_required)
        assert collateral.adapter.join(our_address, eth_required).transact(from_address=our_address)
        flipper.approve(approval_function=hope_directly(), from_address=our_address)
        TestVat.frob(mcd, collateral, our_address, dink=eth_required, dart=Wad(current_bid.tab) + Wad(1))
        lot = current_bid.lot - Wad.from_number(0.2)
        assert flipper.beg() * Ray(lot) <= Ray(current_bid.lot)
        assert mcd.vat.can(our_address, flipper.address)
        TestFlipper.dent(flipper, 1, our_address, lot, current_bid.tab)
        current_bid = flipper.bids(1)
        assert current_bid.guy == our_address
        assert current_bid.bid == current_bid.tab
        assert current_bid.lot == lot

        # Exercise _deal_ after bid has expired
        wait(mcd, our_address, flipper.ttl())
        now = datetime.now().timestamp()
        assert 0 < current_bid.tic < now or current_bid.end < now
        assert flipper.deal(1).transact(from_address=our_address)
        assert len(flipper.active_auctions()) == 0

        # Grab our collateral
        collateral_before = collateral.gem.balance_of(our_address)
        assert collateral.adapter.exit(our_address, current_bid.lot).transact(from_address=our_address)
        collateral_after = collateral.gem.balance_of(our_address)
        assert collateral_before < collateral_after

        # Cleanup
        set_collateral_price(mcd, collateral, Wad.from_number(230))
        # TODO: Determine why this frobbing the art away fails
        TestVat.cleanup_urn(mcd, collateral, our_address)
        TestVat.cleanup_urn(mcd, collateral, other_address)


class TestFlapper:
    @pytest.fixture(scope="session")
    def flapper(self, mcd: DssDeployment) -> Flapper:
        return mcd.flap

    @staticmethod
    def tend(flapper: Flapper, id: int, address: Address, lot: Rad, bid: Wad):
        assert (isinstance(flapper, Flapper))
        assert (isinstance(id, int))
        assert (isinstance(lot, Rad))
        assert (isinstance(bid, Wad))

        assert flapper.live() == 1

        current_bid = flapper.bids(id)
        assert current_bid.guy != Address("0x0000000000000000000000000000000000000000")
        assert current_bid.tic > datetime.now().timestamp() or current_bid.tic == 0
        assert current_bid.end > datetime.now().timestamp()

        assert lot == current_bid.lot
        assert bid > current_bid.bid
        assert (bid >= Wad(flapper.beg()) * current_bid.bid)

        assert flapper.tend(id, lot, bid).transact(from_address=address)

    def test_getters(self, mcd, flapper):
        assert flapper.beg() == Ray.from_number(1.05)
        assert flapper.ttl() > 0
        assert flapper.tau() > flapper.ttl()
        assert flapper.kicks() >= 0

    def test_scenario(self, web3, mcd, flapper, our_address, other_address, deployment_address):
        # Create a CDP with surplus
        collateral = mcd.collaterals[1]
        assert flapper.kicks() == 0
        wrap_eth(mcd, deployment_address, Wad.from_number(0.1))
        assert collateral.adapter.join(deployment_address, Wad.from_number(0.1)).transact(
            from_address=deployment_address)
        TestVat.frob(mcd, collateral, deployment_address, dink=Wad.from_number(0.1), dart=Wad.from_number(10))
        assert mcd.vow.joy() == Rad(0)
        assert mcd.jug.drip(collateral.ilk).transact(from_address=deployment_address)
        # total surplus > total debt + surplus auction lot size + surplus buffer
        assert mcd.vow.joy() > mcd.vow.awe() + mcd.vow.bump() + mcd.vow.hump()
        assert mcd.vow.woe() == Rad(0)
        joy_before = mcd.vow.joy()
        # TODO: Get bid_id return value from transaction rather than guessing bid_id==1
        flap_result = mcd.vow.flap().transact(from_address=deployment_address)
        # print(f"flap_result={flap_result.logs}")
        # assert flap_result.result == 1
        assert flapper.kicks() == 1
        assert len(flapper.active_auctions()) == 1
        current_bid = flapper.bids(1)
        assert current_bid.lot > Rad(0)
        print(f"initial bid={current_bid}")

        # Bid on the surplus
        mint_mkr(mcd.mkr, deployment_address, our_address, Wad.from_number(10))
        flapper.approve(mcd.mkr.address, directly(from_address=our_address))
        bid = Wad.from_number(0.001)
        assert mcd.mkr.balance_of(our_address) > bid
        TestFlapper.tend(flapper, 1, our_address, current_bid.lot, bid)
        current_bid = flapper.bids(1)
        print(f"first bid={current_bid}")
        assert current_bid.bid == bid
        assert current_bid.guy == our_address

        # Exercise _deal_ after bid has expired
        wait(mcd, our_address, flapper.ttl())
        now = datetime.now().timestamp()
        assert 0 < current_bid.tic < now or current_bid.end < now
        assert flapper.deal(1).transact(from_address=our_address)

        # Grab our dai
        assert mcd.dai_adapter.exit(our_address, Wad(current_bid.lot)).transact(from_address=our_address)
        assert mcd.dai.balance_of(our_address) >= Wad(current_bid.lot)
        assert joy_before - mcd.vow.bump() == mcd.vow.joy()
        assert mcd.vow.woe() == Rad(0)
        assert mcd.vow.awe() == Rad(0)


class TestFlopper:
    @pytest.fixture(scope="session")
    def flopper(self, mcd: DssDeployment) -> Flopper:
        return mcd.flop

    @staticmethod
    def dent(flopper: Flopper, id: int, address: Address, lot: Wad, bid: Rad):
        assert (isinstance(flopper, Flopper))
        assert (isinstance(id, int))
        assert (isinstance(lot, Wad))
        assert (isinstance(bid, Rad))

        assert flopper.live() == 1

        current_bid = flopper.bids(id)
        assert current_bid.guy != Address("0x0000000000000000000000000000000000000000")
        assert current_bid.tic > datetime.now().timestamp() or current_bid.tic == 0
        assert current_bid.end > datetime.now().timestamp()

        assert bid == current_bid.bid
        assert lot < current_bid.lot
        assert (Wad(flopper.beg()) * lot) <= current_bid.lot

        assert flopper.dent(id, lot, bid).transact(from_address=address)

    def test_getters(self, mcd, flopper):
        assert flopper.beg() == Ray.from_number(1.05)
        assert flopper.ttl() > 0
        assert flopper.tau() > flopper.ttl()
        assert flopper.kicks() >= 0

    def test_scenario(self, web3, mcd, flopper, our_address, other_address, deployment_address):
        # Create a CDP
        collateral = mcd.collaterals[0]
        ilk = collateral.ilk
        wrap_eth(mcd, deployment_address, Wad.from_number(1))
        assert collateral.adapter.join(deployment_address, Wad.from_number(1)).transact(
            from_address=deployment_address)
        TestVat.frob(mcd, collateral, deployment_address, dink=Wad.from_number(1), dart=Wad(0))
        max_dart = TestVat.max_dart(mcd, collateral, deployment_address) - Wad(1)
        TestVat.frob(mcd, collateral, deployment_address, dink=Wad(0), dart=max_dart)

        # Undercollateralize and bite the CDP
        to_price = Wad(Web3.toInt(collateral.pip.read())) / Wad.from_number(2)
        set_collateral_price(mcd, collateral, to_price)
        urn = mcd.vat.urn(collateral.ilk, deployment_address)
        ilk = mcd.vat.ilk(ilk.name)
        safe = Ray(urn.art) * mcd.vat.ilk(ilk.name).rate <= Ray(urn.ink) * ilk.spot
        assert not safe
        TestCat.simulate_bite(mcd, collateral, deployment_address)
        assert mcd.cat.bite(collateral.ilk, Urn(deployment_address)).transact()
        last_bite = mcd.cat.past_bite(1)[0]
        era_bite = last_bite.era(web3)
        assert era_bite > int(datetime.now().timestamp()) - 10

        # Generate some Dai, bid on and win the flip auction without covering all the debt
        wrap_eth(mcd, our_address, Wad.from_number(10))
        collateral.gem.approve(collateral.adapter.address)
        assert collateral.adapter.join(our_address, Wad.from_number(10)).transact(from_address=our_address)
        web3.eth.defaultAccount = our_address.address
        TestVat.frob(mcd, collateral, our_address, dink=Wad.from_number(10), dart=Wad.from_number(200))
        collateral.flipper.approve(approval_function=hope_directly())
        current_bid = collateral.flipper.bids(1)
        urn = mcd.vat.urn(collateral.ilk, our_address)
        assert Rad(urn.art) > current_bid.tab
        bid = Rad.from_number(150)
        TestFlipper.tend(collateral.flipper, 1, our_address, current_bid.lot, bid)
        mcd.vat.can(our_address, collateral.flipper.address)
        wait(mcd, our_address, collateral.flipper.ttl())
        assert collateral.flipper.deal(1).transact()

        # Raise debt from the queue
        assert mcd.vow.sin_of(era_bite) > Rad(0)
        assert mcd.vow.flog(era_bite).transact()
        assert mcd.vow.sin_of(era_bite) == Rad(0)
        # Cancel out surplus and debt
        assert bid <= mcd.vow.joy()
        assert bid <= mcd.vow.woe()
        assert mcd.vow.heal(bid).transact()

        # Kick off the flop auction
        assert flopper.kicks() == 0
        assert len(flopper.active_auctions()) == 0
        # TODO: Get bid_id return value from transaction rather than guessing bid_id==1
        flop_result = mcd.vow.flop().transact()
        print(f"flop_result={flop_result.logs}")
        current_bid = flopper.bids(1)
        assert flopper.kicks() == 1
        assert len(flopper.active_auctions()) == 1
        assert mcd.vow.woe() >= mcd.vow.sump()
        assert mcd.vow.joy() == Rad(0)

        flopper.approve(mcd.vat.address, hope_directly())
        assert mcd.vat.can(our_address, flopper.address)
        TestFlopper.dent(flopper, 1, our_address, Wad.from_number(0.5), current_bid.bid)
        current_bid = flopper.bids(1)
        assert current_bid.guy == our_address
        print(current_bid)

        wait(mcd, our_address, flopper.ttl())
        assert flopper.live()
        now = int(datetime.now().timestamp())
        assert (current_bid.tic < now and current_bid.tic != 0) or current_bid.end < now
        # FIXME: Issue minting gems to be resolved in DSS 0.2.8
        assert flopper.deal(1).transact(from_address=our_address)
