#File for command shortcuts "make + <command from the list>
.PHONY: gen up down logs test e2e seed compact train diagrams clean

gen:                ## regenerate compose.devices.yml from config/rooms.json
	python3 scripts/gen_compose.py

up: gen             ## build and start everything
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=50 control planner physics

test:               ## unit tests (no Docker needed)
	pytest -q

e2e:                ## end-to-end tests against the running stack
	pytest -q -m e2e tests/

seed:               ## re-register devices + occupancysim room roles (e.g. after `docker compose restart buildsim`)
	docker compose run --rm seed

compact:            ## bronze JSONL -> silver Parquet
	curl -s -X POST localhost:8092/compact

train: compact      ## train the occupancy forecast on recorded data
	python3 -m planner.train --parquet data/silver/sensor.parquet

diagrams:           ## render docs/diagrams/*.d2 -> svg (needs `go install oss.terrastruct.com/d2@latest`)
	for f in docs/diagrams/*.d2; do d2 --theme 0 "$$f" "$${f%.d2}.svg"; done

clean:
	docker compose down -v
	rm -rf data/bronze data/silver
