import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/person.dart';

class UserPeoplePage extends StatefulWidget {
  const UserPeoplePage({super.key});

  @override
  State<UserPeoplePage> createState() => _UserPeoplePageState();
}

class _UserPeoplePageState extends State<UserPeoplePage> {
  List<Person> people = SharedPreferencesUtil().cachedPeople;

  Future<void> _showPersonDialog({Person? person}) async {
    final nameController = TextEditingController(text: person?.name ?? '');
    final formKey = GlobalKey<FormState>();

    await showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(person == null ? 'Add New Person' : 'Edit Person'),
        content: Form(
          key: formKey,
          child: TextFormField(
            controller: nameController,
            decoration: const InputDecoration(labelText: 'Name'),
            validator: (value) {
              if (value == null || value.isEmpty) {
                return 'Please enter a name';
              }
              if (value.length < 2 || value.length > 40) {
                return 'Name must be between 2 and 40 characters';
              }
              if (value.contains(' ')) {
                return 'Name cannot contain spaces';
              }
              return null;
            },
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              if (formKey.currentState!.validate()) {
                if (person == null) {
                  final newPerson = await createPerson(nameController.text);
                  if (newPerson != null) {
                    setState(() {
                      SharedPreferencesUtil().cachedPeople = people;
                      people.add(newPerson);
                    });
                  } else {
                    _showErrorSnackBar('Failed to create person');
                  }
                } else {
                  updatePersonName(person.id, nameController.text);
                  setState(() {
                    final index = people.indexWhere((p) => p.id == person.id);
                    if (index != -1) {
                      people[index] = Person(
                        id: person.id,
                        name: nameController.text,
                        createdAt: person.createdAt,
                        updatedAt: DateTime.now(),
                        speechSamples: person.speechSamples,
                      );
                      SharedPreferencesUtil().replaceCachedPerson(people[index]);
                    }
                  });
                }
                Navigator.pop(context);
              }
            },
            child: Text(person == null ? 'Add' : 'Update'),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmDeletePerson(Person person) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Confirm Deletion'),
        content: Text(
            'Are you sure you want to delete ${person.name}? This will also remove all associated speech samples.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      deletePerson(person.id);
      people.remove(person);
      SharedPreferencesUtil().cachedPeople = people;
    }
  }

  void _showErrorSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('People'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: () => _showPersonDialog(),
          ),
        ],
      ),
      body: ListView.separated(
        itemCount: people.length,
        separatorBuilder: (context, index) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final person = people[index];
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ListTile(
                title: Text(person.name),
                onTap: () => _showPersonDialog(person: person),
                trailing: IconButton(
                  icon: const Icon(Icons.delete, color: Colors.red),
                  onPressed: () => _confirmDeletePerson(person),
                ),
              ),
              if (person.speechSamples != null && person.speechSamples!.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(left: 16, right: 16, bottom: 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Speech Samples:', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                      const SizedBox(height: 4),
                      ...person.speechSamples!.map((sample) => Padding(
                            padding: const EdgeInsets.only(bottom: 4),
                            child: Text(sample, style: const TextStyle(fontSize: 12)),
                          )),
                    ],
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
